from flask import Flask, request, redirect, session, jsonify
import os, requests, math, random, json, re
from datetime import datetime
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps

SECRET_KEY = os.environ['SECRET_KEY']
app = Flask(__name__)
app.config.from_object(__name__)

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
#subaccount_sid = os.environ['TWILIO_SUBACCOUNT_SID']
#master_client = Client(account_sid, auth_token)
client = Client(account_sid, auth_token)
#client = Client(account_sid, auth_token, subaccount_sid)

gmaps = googlemaps.Client(key=os.environ['GOOGLE_MAPS_API_KEY'])

ROUTE_DATA = {
	"start_address":"Goddard Hall",
	"end_address":"Central Park",
	"travel_mode":"driving",
	"arrival_time":"",
	"distance":"",
	"duration":"",
	"steps":[]
}

@app.route("/", methods=['GET', 'POST'])
def hello_world():
	now = datetime.now()
	'''
	directions_result = gmaps.directions("Nashua",
	                                     "Manchester, NH",
	                                     mode="driving",
	                                     departure_time=now)

	print(directions_result)
	'''
	print(gmaps.find_place(["Nashua"], input_type="textquery", fields=["formatted_address"]))
	print(gmaps.places_nearby(query="Manchester", location="42.7654N, 71.4676W", radius=50000))

	'''
	(inner) steps array contains detailed directions for walking or driving steps in transit directions. 
	-------
	Substeps are only available when travel_mode is set to "transit". 
	-------
	The inner steps array is of the same type as steps.

	'''
	'''
	for route in directions_result['legs']:
		for key in route.keys():
			if key != 'steps':
				for step in directions_result['legs'][0][key]:
					text = cleanhtml(step['html_instructions'])
					page += "<b>" + text + "</b>"
					if 'steps' in step:
						for inner_step in step['steps']:
							if 'html_instructions' in inner_step:
								text = cleanhtml(inner_step['html_instructions'])
								if 'distance' in inner_step:
									text += " ({})".format(inner_step['distance']['text'])
								page += "<li>" + text + "</li>"

					else:
						page += "<br><br>"				

			else:				
				page += "Start Address: {}<br>End Address: {} <br><br>"\
						.format(directions_result['legs'][0]['start_address'], directions_result['legs'][0]['end_address'])
	'''

	
	#page = str(directions_result)

	page = ""
	return page
	#return "hello world"

@app.route("/sms", methods=['GET', 'POST'])
def reply_sms():

	resp = MessagingResponse()
	msg = ""

	state = session.get('state', 'init')
	starting_point = session.get('starting_point', '')
	destination = session.get('destination', '')
	mode = session.get('mode', 'driving')


	def navigate():
		nonlocal msg
		resp.message("Loading route ...")
		state = "navigating"

		now = datetime.now()
		directions_result = gmaps.directions(starting_point,
		                                     destination,
		                                     mode=mode,
		                                     departure_time=now)[0]

		total = 0
		for index,step in enumerate(directions_result['legs'][0]['steps'], start=1):
			msg += str(index) + ". " + cleanhtml(step['html_instructions'])
			total += len(str(index) + ". " + cleanhtml(step['html_instructions']))
			if 'distance' in step:
				msg += " ({})".format(step['distance']['text'])
			msg +=  "\n\n"
			if len(msg) > 800:
				resp.message(msg)
				msg = ''
		print(msg)
		print(total)

	incoming_msg = request.values.get('Body', None).lower()

	if incoming_msg == "reset":
		session.clear()
		return ('', 204)

	elif "navigate" in incoming_msg or "directions" in incoming_msg or incoming_msg == "nav":
		msg = "Where from?"
		state = "from?"

	elif "from " in incoming_msg and "to " in incoming_msg:

		mode = ""

		if " by " in incoming_msg:
			mode = incoming_msg.split("by ")[1]
			incoming_msg = incoming_msg.split("by ")[0]

		a_to_b = incoming_msg.split("from ")[1].split(" to ")

		starting_point = a_to_b[0]
		destination = a_to_b[1]
		print("starting_point: " + starting_point)
		print("destination: " + destination)
		
		if not mode:
			mode == "driving"

		navigate()
		

	elif state == "from?":
		starting_point = incoming_msg
		msg = "Where to?"
		state = "to?"

	elif state == "to?":

		destination = incoming_msg
		msg = "Driving, walking, bicycling, or transit?"
		state = "mode?"

	elif state == "mode?":
		mode = incoming_msg.lower()
		navigate()

	session['state'] = state
	session['starting_point'] = starting_point
	session['destination'] = destination

	resp.message(msg)
	return str(resp)

@app.route("/error", methods=['GET', 'POST'])
def sms_reply_error():
    resp = MessagingResponse()
    resp.message("Sorry, I'm having some issues on my end; I promise to fix them as soon as I can!")
    return str(resp)

def formatDirections(directions_result):
	formatted = ""

	for route in directions_result['legs']:
		for key in route.keys():
			if key == 'steps':
				formatted += formatSteps(route[key])

			'''else:
				if 'text' in route[key]:
					val = route[key]['text']
				else:
					val = route[key]				
				formatted += "{}: {}<br><br>"\
						.format(key.replace('_',' ').capitalize(), val)'''
	return formatted

def formatSteps(steps, substeps=False):
	formatted = ""
	for s in steps:
		if 'html_instructions' in s:
			text = cleanhtml(s['html_instructions'])

			if 'distance' in s:
				text += " ({})".format(s['distance']['text'])

			if 'steps' in s:
				text += formatSteps(s['steps'], substeps=True)

			if substeps:
				text = "<li>" + text + "</li>"
			else:
				#text = "<b>" + text + "</b><br><br>"
				text += "<br><br>"

			formatted += text
	formatted = "<ol>" + formatted + "</ol>"
	return formatted


def cleanhtml(raw_html):
  cleanr = re.compile('<.*?>')
  cleantext = re.sub(cleanr, '', raw_html)
  return cleantext

'''
# Geocoding an address
geocode_result = gmaps.geocode('1600 Amphitheatre Parkway, Mountain View, CA')

# Look up an address with reverse geocoding
reverse_geocode_result = gmaps.reverse_geocode((40.714224, -73.961452))
'''

# Request directions via public transit


if __name__ == "__main__":
    app.run(debug=True)