import requests
from datetime import datetime, timedelta
import pytz
import pandas as pd
import json
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib, ssl

def get_measurement_times():
    response = requests.get("https://cfvfdt3cq4.execute-api.eu-west-1.amazonaws.com/test/get-site?site_id=0&start_time_ago=1+DAYS&get_photos=true")
    fills = []
    dates = []
    sensor_ids = []
    container_ids = []
    for container in response.json()["containers"]:
        for date, fill in container["fill"].items():
            fills.append(fill)
            date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S +1")
            dates.append(date)
        sensor_ids += [container["sensor_id"]] * len(container["fill"])
        container_ids += [container["container_id"]] * len(container["fill"])
        
    fill_df = pd.DataFrame({"Fill level": fills, 
                            "Time": dates, 
                            "Sensor": sensor_ids, 
                            "Container": container_ids})
    fill_df = fill_df.sort_values("Time")
    return fill_df

def get_too_late_and_on_time(df, alert_time_hours):
    too_late = {}
    on_time = {}

    for sensor in df.Sensor.unique():
        # Find max time for each sensor
        max_time = df[df.Sensor == sensor].Time.max()
        last_measurement_time = max_time.tz_localize(tz=pytz.timezone('UTC')).astimezone(tz=pytz.timezone('Europe/Oslo'))
        if last_measurement_time < datetime.now(tz=pytz.timezone('Europe/Oslo')) - timedelta(hours=alert_time_hours):
            too_late[str(sensor)] = last_measurement_time.strftime("%Y/%m/%d %H:%M:%S %z")
        else:
            on_time[str(sensor)] = last_measurement_time.strftime("%Y/%m/%d %H:%M:%S %z")

    return too_late, on_time

def save_too_late_json(too_late):
    with open('alert_stored_data.json', 'w') as fp:
        json.dump(too_late, fp, indent=4)

def load_previous_too_late_json():
    try:
        with open('alert_stored_data.json', 'r') as fp:
            return json.load(fp)
    except FileNotFoundError:
        return {}


def get_sensor_htmls(new_errors, old_errors, fixed_errors, on_time):
    
    new_errors_html = ""
    for sensor, ts in new_errors.items():
        new_errors_html += f"<li>{sensor}: {ts}</li>"
    old_errors_html = ""
    for sensor, ts in old_errors.items():
        old_errors_html += f"<li>{sensor}: {ts}</li>"
    working_sensors_html = ""
    for sensor, ts in on_time.items():
        working_sensors_html += f"<li>{sensor}: {ts}</li>"
    fixed_errors_html = ""
    for sensor, ts in fixed_errors.items():
        fixed_errors_html += f"<li>{sensor}: {ts}</li>"

    return new_errors_html, old_errors_html, working_sensors_html, fixed_errors_html


def sort_sensors(too_late, prev_too_late, on_time):
    new_errors = {}
    old_errors = {}
    fixed_errors = {}
    for sensor, ts in too_late.items():
        if sensor in prev_too_late:
            if prev_too_late[sensor] == ts:
                old_errors[sensor] = ts
        else:
            new_errors[sensor] = ts

    for sensor, ts in on_time.items():
        if sensor in prev_too_late:
            if prev_too_late[sensor] == ts:
                del old_errors[sensor]
                fixed_errors[sensor] = ts
    return new_errors, old_errors, fixed_errors, on_time


def construct_email(new_errors, old_errors, fixed_errors, on_time, config):
    if len(new_errors) == 0 and len(fixed_errors):
        subject = f"Sensorita - Fixed sensor errors: {len(fixed_errors)}"
    else:
        subject = f"Sensorita - New sensor errors: {len(new_errors)}"
    
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    receiver_email = "severin@sensorita.com"
    message["To"] = receiver_email

    new_errors_html, old_errors_html, working_sensors_html, fixed_errors_html = get_sensor_htmls(new_errors, old_errors, fixed_errors, on_time)

    # Construct the HTML content
    html_content = f"""
    <html>
    <head></head>
    <body>
        <h2>Sensor status</h2>
        <p>Sends alert if a sensor has not sent a radar sample in {config["alert_time_hours"]} hours or if it starts sending again.</p>
        <p>Sensor number:  "last_measurement_time"</p>
        <h3>New Errors:</h3>
        <ul>
        {new_errors_html}
        </ul>
        <h3>Old Errors:</h3>
        <ul>
        {old_errors_html}
        </ul>
        <h3>Fixed Errors:</h3>
        <ul>
        {fixed_errors_html}
        </ul>
        <h3>Currently working sensors:</h3>
        <ul>
        {working_sensors_html}
        </ul>

        <p>This is an automated message from Sensorita.</p>

    </body>
    </html>
    """

    # Attach the HTML content to the email message
    message.attach(MIMEText(html_content, "html"))

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(
            sender_email, config["emails"], message.as_string()
        )
        print(message.as_string())



def check_new_sensors():
    while True:
        #load config json
        with open("alert_config.json", "r") as f:
            config = json.load(f)
        alert_time_hours = config["alert_time_hours"]
        check_interval_seconds = config["check_interval_minutes"] * 60
        fill_df = get_measurement_times()
        too_late, on_time = get_too_late_and_on_time(fill_df, alert_time_hours)
        prev_too_late = load_previous_too_late_json()
        new_errors, old_errors, fixed_errors, on_time  = sort_sensors(too_late, prev_too_late, on_time)
        
        if len(new_errors) or len(fixed_errors):
            print("New sensors with missing measurements:")
            for sensor in new_errors:
                print(f"- Sensor ID: {sensor}, Last Measurement Time: {new_errors[sensor]}")
            print("SENDING EMAIL:")
            construct_email(new_errors, old_errors, fixed_errors, on_time, config)
        else:
            print("No new sensors with missing measurements")
            print("Working sensors: ")
            for sensor in on_time:
                print(f"- Sensor ID: {sensor}, Last Measurement Time: {on_time[sensor]}")
            
        save_too_late_json(too_late)
        prev_too_late = too_late
        
        time.sleep(check_interval_seconds)  # Sleep for 10 minutes

if __name__ == "__main__":
    
    sender_email = "severin@sensorita.com"
    #password = input("Type your password and press enter:")
    password = "Nastyt-1towne-nuhxyb"
    check_new_sensors()
