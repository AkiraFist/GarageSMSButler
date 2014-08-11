# Garage door opening SMS code developed by Akira Fist, August 2014

# Prereqs:
# - MySQL on the Raspberry Pi, with logins and tables already created
# - Twilio account with some money on it, and a Twilio phone number for SMS.  Each SMS costs under one cent
# - An internet connection on your Pi (duh)
# - Change the phone numbers in the code to your own
# - Add this code to a script, CHMOD 755, then run it

import RPi.GPIO as GPIO
import MySQLdb
import datetime
import time
from contextlib import closing
from twilio.rest import TwilioRestClient

GPIO.setmode(GPIO.BCM) 
GPIO.setup(23, GPIO.OUT)

# VARIABLES

# CHANGE THESE VARIABLES TO YOUR OWN SETTINGS!
# Insert your own account's SID and auth_token from Twilio's account page
twilio_account_sid = "xxxxxxxxxxxxxxxxxxxxxxx"
twilio_auth_token = "yyyyyyyyyyyyyyyyyyyyyyyyyyyy"
# The phone number you purchased from Twilio
sTwilioNumber = "+12145551212"
# Your cell number
sHomeOwnerNumber = "+14695551212"

iNumOpenings = 0
iStatusEnabled = 1
iAuthorizedUser_Count = 0
iSID_Count = 0

sLastCommand = "Startup sequence initiated at {0}.  No open requests, yet".format(time.strftime("%x %X"))
sAuthorized = ""
sSid = ""

# Unfortunately, you can't delete SMS messages from Twilio's list.  
# So we store previously processed SIDs into the database.
lstSids = list()
lstAuthorized = list() # authorized phone numbers, that can open the garage

# Connect to local MySQL database
con = MySQLdb.connect('localhost', 'garage', 'garagepassword', 'GarageDoor')

try:
  # Store authorized phone numbers in a List, so we don't waste SQL resources repeatedly querying tables
  with closing(con.cursor()) as authorized_cursor:
    authorized_users = authorized_cursor.execute("select sPhone from Authorized")   
    auth_rows = authorized_cursor.fetchall()
    for auth_row in auth_rows:
      for auth_col in auth_row:
        iAuthorizedUser_Count = iAuthorizedUser_Count + 1
        lstAuthorized.append(auth_col)

  # Store previous Twilio SMS SID ID's in a List, again, so we don't waste SQL resources repeatedly querying tables
  with closing(con.cursor()) as sid_cursor:
    sid_rows = sid_cursor.execute("select sSid from Door")   
    sid_rows = sid_cursor.fetchall()
    for sid_row in sid_rows:
      for sid_col in sid_row:
        iSID_Count = iSID_Count + 1
        lstSids.append(sid_col)
        
  print "{0} Service loaded, found {1} authorized users, {2} previous SMS messages".format(time.strftime("%x %X"),iAuthorizedUser_Count,iSID_Count)
except:
  print "{0} Error while loading service, bailing!".format(time.strftime("%x %X"))
  if con: con.close() # Not critical since we're bailing, but let's be nice to MySQL
  exit(2)


# Continuously scan Twilio's incoming SMS list
while 1==1:
  # The TRY block is critical.  If we cannot connect to the database, then we could possibly open the garage dozens of times.
  # If we can't contact Twilio, again, we could open the garage excessively.  Ideally, if any error at all occurs, we need
  # to completely bail, and ideally contact the home owner that this application stopped working.
  try:
      
    client = TwilioRestClient(twilio_account_sid, twilio_auth_token)
    # Only process messages from today (Twilio uses UTC)
    messages = client.messages.list(date_sent=datetime.datetime.utcnow())

    for p in messages:
      #print p.sid
      #print p.from_
      #print p.body
      #print p.status

      # Only processed fully received messages, otherwise we get duplicates
      if p.status == "received":
        if p.sid not in lstSids: # Is it a unique SMS SID ID from Twilio's list?
          # Insert this new SID ID into database and List, to avoid double processing
          lstSids.append(p.sid)
          with closing(con.cursor()) as insert_sid_cursor:
            insert_sid_cursor = insert_sid_cursor.execute("insert into Door(sSid) values('{0}')".format(p.sid))
            con.commit()
          
          if p.from_ in lstAuthorized: # Is this phone number authorized to open garage door?
            if p.body.lower() == "kill":
              print "{0} Received KILL command from phone number {1} - bailing now!".format(time.strftime("%x %X"), p.from_)
              sms = client.sms.messages.create(body="Received KILL command from you.  Bailing to terminal now!",to=p.from_,from_=sTwilioNumber)
              sms = client.sms.messages.create(body="Received KILL command from phone number {0}.  Exiting application!".format(p.from_),to=sHomeOwnerNumber,from_=sTwilioNumber)
              exit(3)

            if p.body.lower() == "disable":
              iStatusEnabled = 0
              print "{0} Received STOP command from phone number {1}, now disabled.  Send START to restart".format(time.strftime("%x %X"), p.from_)
              sms = client.sms.messages.create(body="Received STOP command from you.  Send START to restart",to=p.from_,from_=sTwilioNumber)
              sms = client.sms.messages.create(body="Received STOP command from phone number {0}.  Send START to restart".format(p.from_),to=sHomeOwnerNumber,from_=sTwilioNumber)

            if p.body.lower() == "enable":
              iStatusEnabled = 1
              print "{0} Received START command from phone number {1}.  Service is now enabled".format(time.strftime("%x %X"), p.from_)
              sms = client.sms.messages.create(body="Received START command from you.  Service is now enabled",to=p.from_,from_=sTwilioNumber)
              sms = client.sms.messages.create(body="Received START command from phone number {0}.  Service is now enabled".format(p.from_),to=sHomeOwnerNumber,from_=sTwilioNumber)

            if p.body.lower() == "status":
              if iStatusEnabled == 1:
                print "{0} Status requested from {1}, replied".format(time.strftime("%x %X"), p.from_)
                sms = client.sms.messages.create(body="ENABLED.  Status reply: {0}".format(sLastCommand),to=p.from_,from_=sTwilioNumber)
              else:
                print "{0} SERVICE DISABLED!  Status requested from {1}, replied".format(time.strftime("%x %X"), p.from_)
                sms = client.sms.messages.create(body="SERVICE DISABLED!  Status reply: {0}".format(sLastCommand),to=p.from_,from_=sTwilioNumber)
              
            if p.body.lower() == "open":
              if iStatusEnabled == 1:
                iNumOpenings = iNumOpenings + 1
                sLastCommand = "Garage door last opened by {0} on {1}".format(p.from_, time.strftime("%x %X"))
                print "{0} Now opening garage for phone number {1}".format(time.strftime("%x %X"), p.from_)

                # OPEN GARAGE DOOR HERE
                GPIO.output(23, True)
                time.sleep(10)

                sms = client.sms.messages.create(body="Command received, and sent to garage door",to=p.from_,from_=sTwilioNumber)
                print "{0} SMS response sent to authorized user {1}".format(time.strftime("%x %X"), p.from_)
            
                # Replace FROM phone number with your Twilio account's number
                # Replace TO phone with the home owner's number, format: +1 then area code + number
                sms = client.sms.messages.create(body="Garage opened from phone {0}".format(p.from_),to=sHomeOwnerNumber,from_=sTwilioNumber)
                print "{0} SMS sent to home owner with SMS ID = {1}".format(time.strftime("%x %X"), sms.sid)
              else:
                print "{0} Open request received from {1} but SERVICE IS DISABLED!".format(time.strftime("%x %X"), p.from_)
          else: # This phone number is not authorized.  Report possible intrusion to home owner
            print "{0} Unauthorized user tried to access system: {1}".format(time.strftime("%x %X"), p.from_)
            sms = client.sms.messages.create(body="Unauthorized phone tried opening garage: {0}".format(p.from_),to=sHomeOwnerNumber,from_=sTwilioNumber)
            print "{0} SMS sent to home owner with SMS ID = {1}".format(time.strftime("%x %X"), sms.sid)
            
  except:
    print "Error occurred, bailing to terminal"
    exit(1)
    
