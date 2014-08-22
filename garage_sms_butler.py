#!/usr/bin/python

# GARAGE DOOR SMS BUTLER
# Written by Akira Fist, August 2014
#
# Most Raspberry Pi garage door remotes had open ports, or other features I wasn't too fond of. 
# So I created my own that contains much more security, logging of who opens the garage, video capture, garage status and more.
#
# Features:
#
# - 100% secure garage door operation, with access control lists. Only authorized family members can open.
# - Ability to monitor or control garage anywhere in the world from a controlled website, with no open router ports
# - Full video capture of who's coming into the garage, uploaded security to a website for later perusal
# - Ability to remotely stop or kill the process in case of malfunction or abuse
# - Email notifications when a family member arrives or leaves the house
# - Cheap SMS solution (3/4 a cent per text), with no GSM card purchases or any cell contracts
# - Standard Linux code, easily setup on a new Pi, and quickly portable to other platforms like BeagleBone or whatever 
#    future Linux technology arrives. Basically, I wanted the ability to restore this system on a fresh device within 30 minutes or less
#    

import RPi.GPIO as GPIO
import MySQLdb
import datetime
import time
import os
import smtplib
from ftplib import FTP
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
from contextlib import closing
from twilio.rest import TwilioRestClient

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
#                       VARIABLES
#           CHANGE THESE TO YOUR OWN SETTINGS!
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

# Insert your own account's SID and auth_token from Twilio's account page
twilio_account_sid = "xxxxxxxxxxxxxxxxxxxxxxxxxx"
twilio_auth_token = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
# The phone number you purchased from Twilio
sTwilioNumber = "+12145551212"
# Gmail information - for informing homeowner that garage activity happened
recipients = ['myemail@gmail.com', 'home_owner_email@gmail.com']
sGmailAddress = "myemail@gmail.com"
sGmailLogin = "GoogleUserName"
sGmailPassword = "GoogleEmailPassword"
sFTPUserName = "WebsiteFTPUsername"
sFTPPassword = "WebsiteFTPPassword"
sFTPHost = "MyWebsite.com"

iNumOpenings = 0
iStatusEnabled = 1
iAuthorizedUser_Count = 0
iSID_Count = 0

sLastCommand = "Startup sequence initiated at {0}.  No open requests, yet".format(time.strftime("%x %X"))
sAuthorized = ""
sSid = ""
sSMSSender = ""

GPIO_PIN = 23
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_PIN, GPIO.OUT)

# Unfortunately, you can't delete SMS messages from Twilio's list.  
# So we store previously processed SIDs into the database.
lstSids = list()
lstAuthorized = list() # authorized phone numbers, that can open the garage

# Connect to local MySQL database
con = MySQLdb.connect('localhost', 'garage', 'garagepassword', 'GarageDoor')
# Twilio client which will be fetching messages from their server
TwilioClient = TwilioRestClient(twilio_account_sid, twilio_auth_token)


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
#                       FUNCTIONS
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

# This function sends an SMS message, wrapped in some error handling
def SendSMS(sMsg):
  try:
    sms = TwilioClient.sms.messages.create(body="{0}".format(sMsg),to="{0}".format(sSMSSender),from_="{0}".format(sTwilioNumber))
  except:
    print "Error inside function SendSMS"
    pass

# Once the garage door has begun opening, I want a video of who's coming in.  And then, upload the video to my website so I can see it remotely    
def TakeVideoAndUpload():
  try: 
    sVideoFile = "Vid.{0}.h264".format(time.strftime("%m-%d-%Y.%I.%M.%S"))
    # Give 10 seconds to garage to raise up
    time.sleep(10)
    # Now take 60 seconds of video, to see who's coming inside
    sVideoCommand = "raspivid -w 640 -h 480 -o {0} -t 60000".format(sVideoFile)
    os.system(sVideoCommand)
    ftp = FTP(sFTPHost,sFTPUserName,sFTPPassword)    
    ftp.storbinary("stor {0}".format(sVideoFile), open("/home/pi/movies/{0}".format(sVideoFile),'rb'),blocksize=1024)
    # It uploaded ok, so delete the video file to avoid clogging up SD card space
    os.system("sudo rm {0}".format(sVideoFile))
  except:
    print "Error inside function TakeVideoAndUpload"
    pass

# When doing a STATUS on the Garage SMS Butler, it will capture a screen shot of the garage, so I can see if it's open or closed, from anywhere in the world
def TakePictureAndUpload():
  try:
    os.system("raspistill -w 640 -h 480 -o /home/pi/pictures/garagepic.jpg")
    ftp = FTP(sFTPHost,sFTPUserName,sFTPPassword)
    ftp.storbinary("stor garagepic.jpg", open("/home/pi/pictures/garagepic.jpg",'rb'),blocksize=1024)
  except:
    print "Error inside function TakePictureAndUpload"
    pass

# Send a signal to the relay
def OpenGarageDoor():
  try:
    GPIO.output(GPIO_PIN, GPIO.HIGH)
    time.sleep(0.5)
    GPIO.output(GPIO_PIN, GPIO.LOW)
  except:
    print "Error inside function OpenGarageDoor"
    pass

# Email the home owner with any status updates
def SendGmailToHomeOwner(sMsg):
  try:
    connect = server = smtplib.SMTP('smtp.gmail.com:587')
    starttls = server.starttls()
    login = server.login(sGmailLogin,sGmailPassword)
    msg = MIMEMultipart()
    msg['Subject'] = "GARAGE: {0}".format(sMsg)
    msg['From'] = sGmailAddress
    msg['To'] = ", ".join(recipients)
    sendit = server.sendmail(sGmailAddress, recipients, msg.as_string())
    server.quit()
  except:
    print "Error inside function SendGmailToHomeOwner"
    pass


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
  SendGmailToHomeOwner("{0} Service loaded, found {1} authorized users, {2} previous SMS messages".format(time.strftime("%x %X"),iAuthorizedUser_Count,iSID_Count))
except:
  print "{0} Error while loading service, bailing!".format(time.strftime("%x %X"))
  if con: con.close() # Not critical since we're bailing, but let's be nice to MySQL
  exit(2)


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
#                       MAIN GARAGE LOOP
#
#         Continuously scan Twilio's incoming SMS list
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

while (True):
  
  # The TRY block is critical.  If we cannot connect to the database, then we could possibly open the garage dozens of times.
  # If we can't contact Twilio, again, we could open the garage excessively.  Ideally, if any error at all occurs, we need
  # to completely bail, and ideally contact the home owner that this application stopped working.
  try:

    # Only process messages from today (Twilio uses UTC)
    messages = TwilioClient.messages.list(date_sent=datetime.datetime.utcnow())

    for p in messages:
      sSMSSender = p.from_

      # Only processed fully received messages, otherwise we get duplicates
      if p.status == "received":
        if p.sid not in lstSids: # Is it a unique SMS SID ID from Twilio's list?
          # Insert this new SID ID into database and List, to avoid double processing
          lstSids.append(p.sid)
          try:
            with closing(con.cursor()) as insert_sid_cursor:
              insert_sid_cursor = insert_sid_cursor.execute("insert into Door(sSid) values('{0}')".format(p.sid))
              con.commit()
          except:
            print "Error while inserting SID record to database"
            pass
            
          if p.from_ in lstAuthorized: # Is this phone number authorized to open garage door?
            if p.body.lower() == "kill":
              print "{0} Received KILL command from phone number {1} - bailing now!".format(time.strftime("%x %X"), sSMSSender)
              SendSMS("Received KILL command from you.  Bailing to terminal now!")
              SendGmailToHomeOwner("Received KILL command from phone number {0}.  Exiting application!".format(sSMSSender))
              exit(3)

            if p.body.lower() == "disable":
              iStatusEnabled = 0
              print "{0} Received STOP command from phone number {1}, now disabled.  Send START to restart".format(time.strftime("%x %X"), sSMSSender)
              SendSMS("Received STOP command from you.  Send START to restart")
              SendGmailToHomeOwner("Received STOP command from phone number {0}.  Send START to restart".format(sSMSSender))

            if p.body.lower() == "enable":
              iStatusEnabled = 1
              print "{0} Received START command from phone number {1}.  Service is now enabled".format(time.strftime("%x %X"), sSMSSender)
              SendSMS("Received START command from you.  Service is now enabled")
              SendGmailToHomeOwner("Received START command from phone number {0}.  Service is now enabled".format(sSMSSender))

            if p.body.lower() == "status":
              if iStatusEnabled == 1:
                TakePictureAndUpload()
                print "{0} Status requested from {1}, replied".format(time.strftime("%x %X"), sSMSSender)
                SendSMS("ENABLED.  Status reply: {0}".format(sLastCommand))
              else:
                print "{0} SERVICE DISABLED!  Status requested from {1}, replied".format(time.strftime("%x %X"), sSMSSender)
                SendSMS("SERVICE DISABLED!  Status reply: {0}".format(sLastCommand))
              
            if p.body.lower() in ("open","close"):
              if iStatusEnabled == 1:
                iNumOpenings = iNumOpenings + 1
                sLastCommand = "Garage door last opened by {0} on {1}".format(p.from_, time.strftime("%x %X"))
                print "{0} Now opening garage for phone number {1}".format(time.strftime("%x %X"), sSMSSender)

                # OPEN GARAGE DOOR HERE
                SendSMS("Command received, and sent to garage door")
                print "{0} SMS response sent to authorized user {1}".format(time.strftime("%x %X"), sSMSSender)
                OpenGarageDoor()
                TakeVideoAndUpload()
                SendGmailToHomeOwner("Garage opened from phone {0}".format(sSMSSender))
                print "{0} Email sent to home owner".format(time.strftime("%x %X"))
              else:
                print "{0} Open request received from {1} but SERVICE IS DISABLED!".format(time.strftime("%x %X"), sSMSSender)
                
          else: # This phone number is not authorized.  Report possible intrusion to home owner
            print "{0} Unauthorized user tried to access system: {1}".format(time.strftime("%x %X"), sSMSSender)
            SendGmailToHomeOwner("Unauthorized phone tried opening garage: {0}".format(sSMSSender))
            print "{0} Email sent to home owner".format(time.strftime("%x %X"))

  except KeyboardInterrupt:  
    SendGmailToHomeOwner("Application closed via keyboard interrupt (somebody closed the app)")
    GPIO.cleanup() # clean up GPIO on CTRL+C exit  
    exit(4)
  
  except:
    print "Error occurred, bailing to terminal"
    SendGmailToHomeOwner("Error occurred, bailing to terminal")
    GPIO.cleanup()  
    exit(1)
    
GPIO.cleanup()  

