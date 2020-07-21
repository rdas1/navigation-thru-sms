from flask import Flask, request, redirect, session, jsonify
from flask_session import Session
import os, requests, math, random, json, re, time
import redis
import pytz
from datetime import datetime
from lat_lon_parser import parse
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import googlemaps

app = Flask(__name__)
app.config.update(
	SECRET_KEY=os.environ['SECRET_KEY'],
	SESSION_PERMANENT=True,
	SESSION_TYPE="redis",
	SESSION_REDIS=redis.from_url(os.environ['REDIS_URL'])
)
Session(app)

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
#subaccount_sid = os.environ['TWILIO_SUBACCOUNT_SID']
#master_client = Client(account_sid, auth_token)
client = Client(account_sid, auth_token)
#client = Client(account_sid, auth_token, subaccount_sid)

gmaps = googlemaps.Client(key=os.environ['GOOGLE_MAPS_API_KEY'])
GREETINGS = ['yo', 'hello', 'hi', 'howdy', 'start', 'nav', 'navigate', 'directions', 'help']
INSTRUCTIONS = "Ask me for directions between two places, and I'll get the directions from Google Maps! e.g. 'directions from Boston to New York' \n\nOptionally, you can specify if you're walking/using transit by adding 'by walking' or 'by transit' (default mode is driving) \ne.g. 'how do I get from Central Park to the Brooklyn Museum by transit'.\n\nYou can also save locations by typing 'save <address> as <alias>', e.g. 'save 101 Sesame Street as home'! \n\nIf you're really lost, you can copy your latitude and longitude from the Compass app on your phone and paste it here as your start location."

def cleanhtml(raw_html):
  cleanr = re.compile('<.*?>')
  cleantext = re.sub(cleanr, '', raw_html)
  cleantext = cleantext.replace("&nbsp", " ")
  cleantext = cleantext.replace("Destination", " Destination")
  return cleantext

def send_message(msg):
		client.messages.create(
			from_=os.environ['TWILIO_NUMBER'],
			body=msg,
			to=session['number'])

def nav(parsed, resp):

	start = parsed.group("start")
	destination = parsed.group("destination")

	saved_locations_dict = session.get("saved_locations", {})

	if start in saved_locations_dict:
		start = saved_locations_dict[start]
	if destination in saved_locations_dict:
		destination = saved_locations_dict[destination]

	if "°" in start and '″ ' in start:
		if "″ S" in start:
			start = "-" + start
		lat = re.split('n |s ', start)[0]
		lon = re.split('n |s ', start)[1]
		if "″ W" in lon:
			lon = "-" + lon
		lat = str(parse(lat))
		lon = str(parse(lon))
		try:
			start = gmaps.reverse_geocode((lat,lon), "street_address")[0]["formatted_address"]
			print("START: " + start)
		except:
			resp.message("Google Maps couldn't find anything at those coordinates :/")
			return str(resp)

	if parsed.group("mode"):
		mode = parsed.group("mode")
	else:
		mode ="driving"
	
	try:
		directions_result = gmaps.directions(start,
											destination,
											mode=mode,
											departure_time=datetime.now())[0]
		session["steps_data"] = directions_result['legs'][0]['steps']
	except (IndexError, googlemaps.exceptions.ApiError):
		resp.message("Location/Route not found -- try being more specific")
		return str(resp)

	msg = "Trip Duration: {}\n".format(directions_result['legs'][0]['duration']['text'])
	for index,step in enumerate(directions_result['legs'][0]['steps'], start=1):
		if len(msg) > 1500:
			send_message(msg + " ...")
			msg = '...'
		if 'html_instructions' in step:
			msg += "\n{}. {}".format(index, cleanhtml(step['html_instructions']))
		if 'distance' in step:
			msg += " ({})".format(step['distance']['text'])
		if 'transit_details' in step:
			if 'name' in step['transit_details']['line']:
				transit_name = step['transit_details']['line']['name']
			else:
				transit_name = step['transit_details']['line']['short_name']
			msg += "\n Take {} toward {} {} stop(s) to {}".format(transit_name, step['transit_details']['headsign'], step['transit_details']['num_stops'], step['transit_details']['arrival_stop']['name'])
		if 'steps' in step:
			msg += " -- type 'expand {}' to see more details for this step".format(index)
		msg += "\n"
		print(msg)

	resp.message(msg)
	return str(resp)

def expand(parsed, resp):
	steps_data = session.get("steps_data")

	if steps_data is None:
		resp.message("Sorry, there's no directions to expand :/")
		return str(resp)

	num_to_expand = int(parsed.group("num_to_expand"))
	step_to_expand = steps_data[num_to_expand-1]

	if 'steps' in step_to_expand:
		msg = "{}: \n".format(cleanhtml(step_to_expand['html_instructions']))
		for index,step in enumerate(step_to_expand['steps'], start=1):
			if len(msg) > 1500:
				send_message(msg + " ...")
				msg = '...'
			if 'html_instructions' in step:
				msg += "\n{}. {}".format(index, cleanhtml(step['html_instructions']))
			if 'distance' in step:
				msg += " ({})".format(step['distance']['text'])
			if 'transit_details' in step:
				msg += "\n-- Take {} {} stop(s) to {}".format(step['transit_details']['line']['name'], step['transit_details']['num_stops'], step['transit_details']['arrival_stop']['name'])
			if 'steps' in step:
				msg += " -- type 'expand {}' to see more details for this step".format(index)
			msg += "\n"
		resp.message(msg)
	else:
		resp.message("Nothing to expand!")
	
	return str(resp)

def save_location(parsed, resp):

	alias = parsed.group("alias")
	location_to_save = parsed.group("location_to_save")

	saved_locations_dict = session.get("saved_locations", {})

	try:
		location_to_save = gmaps.find_place(location_to_save, input_type="textquery", fields=["formatted_address"])["candidates"][0]["formatted_address"]
		if alias in saved_locations_dict and saved_locations_dict[alias] == location_to_save:
			resp.message("{} is already saved as {}!".format(location_to_save, alias))
			return str(resp)
		saved_locations_dict[alias] = location_to_save
		session["saved_locations"] = saved_locations_dict
		resp.message("Saved {} as {}!".format(location_to_save, alias))
	except IndexError:
		resp.message("Couldn't find any location '{}'".format(location_to_save))
	return str(resp)

def list_saved_locations(parsed, resp):
	saved_locations_dict = session.get("saved_locations", {})
	if not saved_locations_dict:
		resp.message("No locations saved -- to save a location, type 'save <location> as <alias>', e.g. 'save The Shire as home'")
		return str(resp)
	resp.message(str(saved_locations_dict))
	return str(resp)

@app.route("/", methods=['GET', 'POST'])
def hello_world():
	return "hello world"

@app.route("/sms", methods=['GET', 'POST'])
def reply_sms():

	incoming_msg = request.values.get('Body', None).lower()
	session['number'] = request.form['From']

	resp = MessagingResponse()

	if incoming_msg in GREETINGS:
		resp.message("Hello! I'm NavBot.\n\nAsk me for directions between two places, and I'll get the directions from Google Maps!\ne.g. 'Boston to New York'")
		resp.message("Optionally, you can specify if you're walking/using transit by adding 'by walking' or 'by transit' (default mode is driving) \ne.g. 'how do I get from Central Park to the Brooklyn Museum by transit?'\n\nYou can also save locations by typing 'save <address> as <alias>', e.g. 'save 101 Sesame Street as home'!\n\nIf you're really lost, you can copy your latitude and longitude from the Compass app on your phone and paste it here as your start location.")
		return str(resp)

	COMMANDS = {
		r"(?:how do i get |directions |how to get )?to (?!get )(?P<destination>.+) from (?P<start>.+?)( by (?P<mode>walking|transit))?( (?P<timetype>at|before) (?P<time>\d{1,2}(?:(?:am|pm)|(?::\d{1,2})(?:am|pm)?)))?\??$": nav,
		r"(?:how do i get |directions |how to get )?from (?P<start>.+) to (?P<destination>.+?)( by (?P<mode>walking|transit))?( (?P<timetype>at|before) (?P<time>\d{1,2}(?:(?:am|pm)|(?::\d{1,2})(?:am|pm)?)))?\??$": nav,
		r"(?:directions )?(?P<start>.+) to (?P<destination>.+?)( by (?P<mode>walking|transit))?( (?P<timetype>at|before) (?P<time>\d{1,2}(?:(?:am|pm)|(?::\d{1,2})(?:am|pm)?)))?\??$": nav,
		r"expand (?P<num_to_expand>\d+)$": expand,
		r"save (?P<location_to_save>.+) as (?P<alias>.+?)\.?$": save_location,
		"saved locations": list_saved_locations
	}

	for cmd,fnc in COMMANDS.items():
		parsed = re.search(cmd, incoming_msg)
		if parsed:
			send_message("Loading...")
			return fnc(parsed, resp)

	if parsed is None:
		resp.message("Sorry, I didn't get that :/")
		resp.message(INSTRUCTIONS)
		return str(resp)

@app.route("/error", methods=['GET', 'POST'])
def sms_reply_error():
	resp = MessagingResponse()
	resp.message("Sorry, I'm having some issues on my end; I promise to fix them as soon as I can!")
	return str(resp)

if __name__ == "__main__":
	app.run(debug=True)