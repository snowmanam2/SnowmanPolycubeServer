from pydantic import BaseModel
from typing import Optional, List

class job_schema(BaseModel):
	startdate: int
	seedurl: str
	seedcount: int
	seedchunk: int
	seedlength: int
	targetlength: int
	tickettimeout: int

class job_schema_db(job_schema):
	job: str

class ticket_schema(BaseModel):
	ticketid: int
	job: str
	token: str
	seedindex: int
	seedchunk: int
	seedurl: str
	targetlength: int

class result_schema(BaseModel):
	resultlength: int
	resultvalue: int

class submission_schema(BaseModel):
	ticketid: int
	token: str
	contributor: str
	seedindex: int
	secondselapsed: int
	results: List[result_schema] = []

class submission_schema_db(BaseModel):
	submissionid: int
	job: str
	seedindex: int
	contributor: str
	secondselapsed: int
	ip: str
	receivedate: int
	status: int
	results: List[result_schema] = []

class submission_update_schema(BaseModel):
	status: int
	contributor: str
	
class results_schema(BaseModel):
	seedindices: List[int] = []
	values: List[int] = []
	
class summary_schema(BaseModel):
	value: int
	seconds: int
	resultcount: int
	jobcount: int
	targetlength: int