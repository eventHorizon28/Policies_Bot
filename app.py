#Danil Skachkov's weather webhook really helped me build my own webhook for the hr_policies chatbot
#Check it out here: https://github.com/xVir/apiai-python-webhook

from __future__ import print_function
from future.standard_library import install_aliases
install_aliases()

import urllib2
import json
import os
import psycopg2
import dbconnect
import PageCred
import requests
import gspread

from oauth2client import service_account
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
from flask import request
from flask import make_response
from bs4 import BeautifulSoup


# Flask app should start in global layout
app = Flask(__name__)


@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    print(json.dumps(req, indent=4))

    res = processRequest(req)
    
    res = json.dumps(res, indent=4)
    # print(res)
    r = make_response(res)
    r.headers['Content-Type'] = 'application/json'
    return r


def processRequest(req):
    #if the request is to get the number of leaves
    Ltype = req.get("result").get("parameters").get("leave_type")
    if(req.get("originalRequest").get("source") == "facebook" and (Ltype == "sick" or Ltype == "casual" or Ltype == "privilege")):
        #fetch name of the user from facebook and fetch the user's leave balance from the google sheets
        uid = req.get("originalRequest").get("data").get("sender").get("id")
        r = fetchFB(uid)
        firstN = r.get("first_name")
        lastN = r.get("last_name")
        speech = fetchBal(firstN, lastN, Ltype)
        return {
        "speech": speech,
        "displayText": speech,
        #"data": {},
        # "contextOut": [],
        "source": "hr_policies"
        }
        
    
    policy = req.get("result").get("parameters").get("intent")
    query = req.get("result").get("resolvedQuery")
    
    #getting the default response from api.ai "I cannot understand" and the likes
    default = req.get("result").get("fulfillment").get("speech")
    if policy == "":
        #if the intent name in api.ai is blank
        print("please include parameter \"intent\" with the name of policy as given in the document")
        return {}
    
    #this is executed if there is some valid intent other than leave balance intent
    res = makeWebhookResult(policy, query, default)
    return res


def makeWebhookResult(pol, query, default):
    
    #open the google doc webpage and parse the html
    URL = "https://goo.gl/LKrJSz"
    
    web = urllib2.urlopen(URL)
    html = web.read()
    
    soup = BeautifulSoup(html, "html.parser")

    #In the google docs I inserted everything into a table
    tables = soup.findAll("table")
    tabList = []
    id=[]
    i=0
	
    for tag in soup.findAll("h2"):
        #get ids of all the headings
        id.append(tag.get('id'))
        
    for table in tables:
        #store all data from the document in a list
    	tabList.append(table.getText())
    
    #if the policy exists in the list(made from the document) speech = pol+1 , else speech = default response by api.ai
    try:
        if pol in tabList:
            i = tabList.index(pol)
            speech = tabList[i+1]
            if(len(speech) > 160):
                speech = speech[0:160]+"... "
                speech+=" \nFor more info on this, go to: "+URL
                speech+="#"+str(id[((i+1)/2)])

        dbManage(query, speech)
    except:
        #if it does not, store the conversation in db for analysis anyway
        print(default)
        dbManage(query, default)

    return {
        "speech": speech,
        "displayText": speech,
        #"data": {},
        # "contextOut": [],
        "source": "hr_policies"
    }

def dbManage(query, text):
    db = psycopg2.connect(
    database=dbconnect.database,
    user=dbconnect.user,
    password=dbconnect.password,
    host=dbconnect.host,
    port=dbconnect.port)
    
    #adding the query and the response to the db
    x = "db made"+dbconnect.database
    with db:
        cur = db.cursor()
        cur.execute("CREATE TABLE if not exists BOT(Query TEXT, Response TEXT)")
        cur.execute("INSERT INTO BOT (Query, Response) VALUES(%s,%s)", (query, text))
        
        
def fetchFB(uid):
    #fields = "name, first_name"
    access_token = PageCred.Access_Token
    url = "https://graph.facebook.com/v2.6/"+uid
    params = {'fields':'first_name, last_name', 'access_token':access_token}
    r = requests.get(url, params).json()
    print("json fetched from fb =")
    print(r)
    return r

#to fetch leave balance from google spreadsheet
def fetchBal(first, last, l_type):
    scope = ['https://spreadsheets.google.com/feeds']
    creds = service_account.ServiceAccountCredentials.from_json_keyfile_name('employees_leave.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("Leave Balance").sheet1
    #list_of_hashes = sheet.get_all_records()       --to get ALL the records
    columnNames = sheet.row_values(1)
    print(columnNames)
    
    columnNames = [item.lower() for item in columnNames]
    lastnameColumn = 1+(columnNames.index("first name"))
    firstnameColumn = 1+(columnNames.index("last name"))
    
    firstnameColumn +=1 # is equal to 1!!!!!!!!!!!!!
    lastnameColumn+=1 #is equal to 6!!!!!!!!!!!!!!!!
    #index+1 because elements in list start with 0, but in spreadsheet start with 1
    print(firstnameColumn)
    print(lastnameColumn)
    
    #to determine the col of requested leave type 
    if(l_type == "sick"):
        leaveCol = 1+(columnNames.index("sick leaves"))
    elif(l_type == "casual"):
        leaveCol = 1+(columnNames.index("casual leaves"))
    elif(l_type == "privilege"):
        leaveCol = 1+(columnNames.index("privilege leaves"))
    
    lastN = []
    mptCount =0
    #eliminating empty list items added from empty cells (if three consecutive empty rows - break: 3 just to be more sure that the table is empty now onwards)
    for names in sheet.col_values(1):
        if(len(names)>0):
            lastN.append(names)
            mptCount=0
        else:
            mptCount +=1
            if(mptCount >= 3):
                break
    print(lastN)
    
    i = 1
    for user in lastN:
        if(user == last):
            if(sheet.cell(i, firstnameColumn).value == first):
                speech = ""+sheet.cell(i,firstnameColumn).value+", your "+l_type+" leave balance is "+sheet.cell(i,leaveCol).value+" days."
                break
        i=i+1
    return speech

#to run locally - 
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))

    print("Starting app on port %d" % port)

app.run(debug=False, port=port, host='0.0.0.0')
