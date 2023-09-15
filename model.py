from sqlalchemy.schema import Column 
from sqlalchemy.types import String, Integer, Text, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
from database import Base

class Job(Base):
	__tablename__ = "jobs"
	job = Column(String(32), primary_key=True)
	startdate = Column(Integer)
	seedurl = Column(String(255))
	seedcount = Column(Integer)
	seedchunk = Column(Integer)
	seedlength = Column(Integer)
	targetlength = Column(Integer)
	tickettimeout = Column(Integer)
	segments = relationship('JobSegment', backref='jobs')
	
class JobSegment(Base):
	__tablename__ = "jobsegments"
	id = Column(Integer, primary_key=True, index=True)
	job = Column(String(32), ForeignKey('jobs.job'))
	seedindex = Column(Integer)
	
class Ticket(Base):
	__tablename__ = "tickets"
	ticketid = Column(Integer, primary_key=True, index=True)
	job = Column(String(32))
	issuedate = Column(Integer)
	token = Column(String(255))
	seedindex = Column(Integer)
	ip = Column(String(48))
	
class Submission(Base):
	__tablename__ = "submissions"
	submissionid = Column(Integer, primary_key=True, index=True)
	job = Column(String(32))
	seedindex = Column(Integer)
	contributor = Column(String(32))
	secondselapsed = Column(Integer)
	ip = Column(String(48))
	receivedate = Column(Integer)
	status = Column(Integer)
	results = relationship('Result', backref='submissions')
	
class Result(Base):
	__tablename__ = "results"
	resultid = Column(Integer, primary_key=True, index=True)
	submissionid = Column(Integer, ForeignKey('submissions.submissionid'))
	resultlength = Column(Integer)
	resultvalue = Column(BigInteger)