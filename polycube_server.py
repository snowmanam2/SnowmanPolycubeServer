from fastapi import FastAPI, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from model import *
from schema import *
from session import create_get_session
import os
import time
import secrets

API_KEY = os.environ.get('API_KEY')
api_key_query = APIKeyQuery(name="api-key", auto_error=False)
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def get_api_key(
	api_key_query: str = Security(api_key_query),
	api_key_header: str = Security(api_key_header),
) -> str:
	if api_key_query == API_KEY:
		return api_key_query
	elif api_key_header == API_KEY:
		return api_key_header
	else:
		raise HTTPException(status_code=401, detail="Invalid or missing API key")

app = FastAPI()

# Public: Job Listing
@app.get("/jobs", response_model=List[job_schema_db], status_code=200)
async def get_jobs(db: Session = Depends(create_get_session)):
	jobs = db.query(Job).all()
	return jobs

# Restricted: Add new job
@app.post("/jobs", response_model=job_schema_db, status_code=201)
async def create_job(j: job_schema_db, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j.job)
	if job_db:
		raise HTTPException(status_code=409, detail="Job already exists.")
	
	new_job = Job(
		job = j.job,
		startdate = j.startdate,
		seedurl = j.seedurl,
		seedcount = j.seedcount,
		seedchunk = j.seedchunk,
		seedlength = j.seedlength,
		targetlength = j.targetlength,
		tickettimeout = j.tickettimeout
	)
	db.add(new_job)
	
	data = [JobSegment(job = j.job, seedindex = i) for i in range(0, j.seedcount, j.seedchunk)]
	db.add_all(data)
	db.commit()
	
	return new_job

# Public: Get job	
@app.get("/jobs/{job}", response_model=job_schema_db, status_code=200)
async def get_job(job: str, db: Session = Depends(create_get_session)):
	job_db = db.query(Job).get(job)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
	
	return job_db
	
# Restricted: Update job
@app.patch("/jobs/{job}", response_model=job_schema_db, status_code=200)
async def update_job(job: str, j: job_schema, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(job)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
	
	job_db.startdate = j.startdate
	job_db.seedurl = j.seedurl
	job_db.seedcount = j.seedcount
	job_db.seedchunk = j.seedchunk
	job_db.seedlength = j.seedlength
	job_db.targetlength = j.targetlength
	job_db.tickettimout = j.tickettimeout
	
	db.commit()
	db.refresh(job_db)
	
	return job_db

# Restricted: Delete job
@app.delete("/jobs/{job}", status_code=200)
async def delete_job(job: str, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(job)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	db.query(JobSegment).where(JobSegment.job == job).delete(synchronize_session=False)
	db.delete(job_db)
	db.commit()
	
	return None

# Public: Open a ticket
@app.post("/jobs/{j}/job-tickets", response_model = ticket_schema, status_code=201)
async def open_ticket(j: str, request: Request, db: Session = Depends(create_get_session)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
	
	result = db.execute(text('''
		SELECT jobsegments.seedindex 
		FROM jobsegments
		WHERE jobsegments.job = :j
		AND jobsegments.seedindex NOT IN 
		( SELECT tickets.seedindex FROM tickets WHERE tickets.job = :j AND tickets.issuedate > :expiration ) 
		AND jobsegments.seedindex NOT IN 
		( SELECT submissions.seedindex FROM submissions WHERE submissions.job = :j AND submissions.status = 0) 
		ORDER BY jobsegments.seedindex ASC'''), {'j': j,  'expiration': int(time.time()) - job_db.tickettimeout}).fetchone()
	
	if not result:
		raise HTTPException(status_code=409, detail="No tickets to make")
		
	new_token = secrets.token_hex()
	
	ticket = Ticket(
		job = j,
		issuedate = int(time.time()),
		token = new_token,
		seedindex = result[0],
		ip = request.client.host
	)
	db.add(ticket)
	db.commit()
	db.refresh(ticket)
	
	client_ticket = {
		'ticketid': ticket.ticketid,
		'job': j,
		'token': new_token,
		'seedindex': ticket.seedindex,
		'seedchunk': job_db.seedchunk,
		'seedurl': job_db.seedurl,
		'targetlength': job_db.targetlength
	}
	
	return client_ticket
	
# Public: Submit ticket results
@app.put("/jobs/{j}/job-tickets", status_code=200)
async def submit_ticket(j: str, sub: submission_schema, request: Request, db: Session = Depends(create_get_session)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
	
	ticket_db = db.query(Ticket).get(sub.ticketid)
	if not ticket_db:
		raise HTTPException(status_code=404, detail="Ticket does not exist")
	if sub.token != ticket_db.token:
		raise HTTPException(status_code=400, detail="Ticket token mismatch")
	
	# We need to check for duplicate submissions
	# but we keep the new submission because the previous submissions might need to be replaced if found invalid
	status = 0
	duplicates_q = db.query(Submission).where(
		Submission.seedindex == ticket_db.seedindex, 
		Submission.status == 0, 
		Submission.job == j)
	if duplicates_q.all():
		status = 1
	
	if len(sub.results) != (job_db.targetlength - job_db.seedlength):
		raise HTTPException(status_code=400, detail="Incorrect result count")
		
	if sub.results[0].resultvalue == 0:
		raise HTTPException(status_code=400, detail="Empty result")
	
	elapsed = time.time() - ticket_db.issuedate
	
	if elapsed < 10:
		raise HTTPException(status_code=400, detail="Ticket returned too quickly")
		
	if (elapsed + 3) < results.secondselapsed:
		raise HTTPException(status_code=400, detail="Invalid compute duration received")
		
	if sub.seedindex != ticket_db.seedindex:
		raise HTTPException(status_code=400, detail="Incorrect seedindex")
	
	new_submission = Submission(
		job = j,
		seedindex = ticket_db.seedindex,
		contributor = sub.contributor,
		secondselapsed = sub.secondselapsed,
		ip = request.client.host,
		receivedate = int(time.time()),
		status = status
	)
	
	db.add(new_submission)
	db.commit()
	db.refresh(new_submission)
	
	db.delete(ticket_db)
	
	results = [
		Result(
			submissionid = new_submission.submissionid, 
			resultlength = r.resultlength, 
			resultvalue = r.resultvalue
		) for r in sub.results]
	
	db.add_all(results)
	db.commit()
	
	return None

# Restricted: View raw job submission data
@app.get("/jobs/{j}/submissions", response_model = List[submission_schema_db], status_code=200)
async def list_submissions(j: str, seedindex: int = 0, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	return db.query(Submission).where(Submission.job == j, Submission.seedindex == seedindex).all()
	
# Restricted: View raw submission information
@app.get("/jobs/{j}/submissions/{s}", response_model = submission_schema_db, status_code=200)
async def get_submission(j: str, s: int, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
	
	submission_db = db.query(Submission).get(s)
	if not submission_db:
		raise HTTPException(status_code=404, detail="Submission does not exist")
	
	return submission_db

# Restricted: Add submission directly bypassing ticket system
@app.post("/jobs/{j}/submission", response_model = submission_schema_db, status_code=201)
async def add_submission(j: str, sub: submission_schema, request: Request, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	status = 0
	duplicates_q = db.query(Submission).where(
		Submission.seedindex == sub.seedindex, 
		Submission.status == 0, 
		Submission.job == j)
	if duplicates_q.all():
		status = 1
	
	new_submission = Submission(
		job = j,
		seedindex = sub.seedindex,
		contributor = sub.contributor,
		secondselapsed = sub.secondselapsed,
		ip = request.client.host,
		receivedate = int(time.time()),
		status = status
	)
	
	db.add(new_submission)
	db.commit()
	db.refresh(new_submission)
	
	results = [
		Result(
			submissionid = new_submission.submissionid, 
			resultlength = r.resultlength, 
			resultvalue = r.resultvalue
		) for r in sub.results]
	
	db.add_all(results)
	db.commit()
	
	return new_submission
	
	
	
# Restricted: Update submission data
@app.patch("/jobs/{j}/submissions/{s}", response_model = submission_schema_db, status_code=200)
async def update_submission(j: str, s: int, sub_update: submission_update_schema, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	submission_db = db.query(Submission).get(s)
	if not submission_db:
		raise HTTPException(status_code=404, detail="Submission does not exist")
		
	submission_db.status = sub_update.status
	submission_db.contributor = sub_update.contributor
	
	db.commit()
	db.refresh(submission_db)
	
	return submission_db

# Restricted: Get results by job / length
@app.get("/jobs/{j}/results/{l}", response_model = results_schema, status_code=200)
async def get_results(j: str, l: int, db: Session = Depends(create_get_session), api_key: str = Security(get_api_key)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	result = db.execute(text('''
		SELECT sub.seedindex, rs.resultvalue
		FROM results rs
		INNER JOIN submissions sub
		ON rs.submissionid = sub.submissionid
		AND rs.resultlength = :l
		AND sub.job = :j
		AND sub.status = 0
		ORDER BY sub.seedindex'''), {'j': j,  'l': l}).fetchall()
	
	seedindices = []
	values = []
	
	for row in result:
		seedindices.append(row.seedindex)
		values.append(row.resultvalue)
		
	return {'seedindices':seedindices, 'values':values}

# Public: Job summary
@app.get("/jobs/{j}/summary", response_model = summary_schema, status_code=200)
async def get_summary(j: str, db: Session = Depends(create_get_session)):
	job_db = db.query(Job).get(j)
	if not job_db:
		raise HTTPException(status_code=404, detail="Job does not exist")
		
	result = db.execute(text('''
		SELECT
		  SUM(rs.resultvalue) value
		, SUM(sub.secondselapsed) seconds
		, COUNT(rs.resultvalue) resultcount
		, MAX(CEILING(jobs.seedcount * 1.0 / jobs.seedchunk)) AS jobcount
		FROM results rs
		INNER JOIN submissions sub
		ON rs.submissionid = sub.submissionid
		AND sub.job = :j
		AND sub.status = 0
		INNER JOIN jobs
		ON jobs.job = sub.job
		AND rs.resultlength = jobs.targetlength'''), {'j': j}).fetchone()
		
	return {'value': result.value, 'seconds': result.seconds, 'resultcount': result.resultcount, 'jobcount': result.jobcount, 'targetlength': job_db.targetlength}
	
