import time
import json
import Adafruit_DHT
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
import pigpio
from gpiozero import Servo
from threading import Timer


FAN_PIN = 6
LIGHT_PIN = 16
PIR_PIN = 26
FLAME_SENSOR_PIN = 24
BUZZER_PIN = 22
LDR_PIN = 17
LEDS_PIN = 27
RAIN_SENSOR_PIN = 23
SERVO_PIN = 12

pi = pigpio.pi()
if not pi.connected:
	exit()
	

SERVO_MIN = 500
SERVO_MAX = 2500
SPEED = 0.01


GPIO.setmode(GPIO.BCM)
GPIO.setup(LIGHT_PIN, GPIO.OUT, initial= GPIO.HIGH)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(FLAME_SENSOR_PIN, GPIO.IN)
GPIO.setup(LDR_PIN, GPIO.IN)
GPIO.setup(LEDS_PIN, GPIO.OUT, initial = GPIO.HIGH)
GPIO.setup(RAIN_SENSOR_PIN, GPIO.IN)



# MQTT setup
MQTT_BROKER = "192.168.1.9"
MQTT_PORT = 1883
MQTT_TOPIC_PUB = "home/temperature"
MQTT_TOPIC_SUB = "home/control"
MQTT_TOPIC_MOTION= "home/motion"
MQTT_TOPIC_FLAME = "home/flame"
MQTT_TOPIC_LDR = "home/ldr"
MQTT_TOPIC_RAIN = "home/rain"
MQTT_USERNAME = "reem10"
MQTT_PASSWORD = "1234567Me"


# DHT sensor setup
DHT_SENSOR = Adafruit_DHT.DHT11
DHT_PIN = 5

auto_mode = False
TEMP_THRESHOLD = 30.0
HUM_THRESHOLD = 40.0

PUBLISH_INTERNVAL = 7
MOTION_TIMER_INTERVAL = 10
motion_timer = None
flame_alert = False

def on_connect(client, userdata, flags, rc):
	if rc == 0:
		print("Connected to MQTT broker")
		client.subscribe(MQTT_TOPIC_SUB)
	else:
		print(f"Failed to connect, return code {rc}")

		
def on_message(client, usedata, msg):
	global auto_mode, flame_alert
	print(f"Message received:{msg.topic} {msg.payload}")
	payload = json.loads(msg.payload.decode('utf-8'))
	if 'auto_mode' in payload:
		auto_mode = payload['auto_mode']
		print(f"Auto mode set to: {auto_mode}")
	if 'fan' in payload:
		if payload['fan'] == "on":
			GPIO.setup(FAN_PIN, GPIO.OUT)
			GPIO.output(FAN_PIN, GPIO.LOW)
			print("Fan turned on")
		elif payload['fan'] == "off":
			GPIO.cleanup(FAN_PIN)
			print("Fan turned OFF")
	if 'light' in payload:
		if payload['light'] == "on":
			GPIO.output(LIGHT_PIN, GPIO.LOW)
			print("Light turned ON")
			
		elif payload['light'] == "off":
			GPIO.output(LIGHT_PIN, GPIO.HIGH)
			print("Light turned OFF")
	if 'buzzer' in payload:
		if payload['buzzer'] == "off":
			GPIO.setup(BUZZER_PIN, GPIO.OUT)
			GPIO.output(BUZZER_PIN, GPIO.HIGH)
			GPIO.cleanup(BUZZER_PIN)
			print("Buzzer turned OFF")
			flame_alert = True
	if 'leds' in payload:
		if payload['leds'] == "off":
			GPIO.output(LEDS_PIN, GPIO.HIGH)
			print("LEDs turned OFF")
		elif payload['leds'] == "on":
			GPIO.output(LEDS_PIN, GPIO.LOW)
			print("LEDs turned ON")
	if 'windows' in payload:
		if payload['windows'] == "close":
			close_windows()
		elif payload['windows'] == "open":
			open_windows()
			
			
def read_sensor():
	humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
	return humidity, temperature
	
def publish_sensor_data(client):
	humidity, temperature = read_sensor()
	if humidity is not None and temperature is not None:
		payload = {
		'temperature': temperature,
		'humidity': humidity,
		'timestamp': int(time.time())
		}
		client.publish(MQTT_TOPIC_PUB, json.dumps(payload))
		print(f"Published: {json.dumps(payload)}")
		
def control_fan(humidity, temperature):
	if auto_mode:
		if temperature > TEMP_THRESHOLD or humidity > HUM_THRESHOLD:
			GPIO.setup(FAN_PIN, GPIO.OUT)
			GPIO.output(FAN_PIN, GPIO.LOW)
			print("Fan turned ON by auto mode")
			
		else:
			GPIO.cleanup(FAN_PIN)
			print("Fan turned OFF by auto mode")
			
def motion_timer_expired():
	global motion_timer
	GPIO.output(LIGHT_PIN, GPIO.HIGH)
	print("Motion timer expired, light turned OFF")
	motion_timer = None
			
def detect_motion(client):
	global motion_timer
	if auto_mode:
		if GPIO.input(PIR_PIN):
			print("Motion detected")
			GPIO.output(LIGHT_PIN, GPIO.LOW)
			payload = {
			'motion': 'detected',
			'timestamp': int(time.time())
			}
			client.publish(MQTT_TOPIC_MOTION, json.dumps(payload))
			print(f"Published motion detected: {json.dumps(payload)}")
			if motion_timer:
				motion_timer.cancel()
			motion_timer = Timer(MOTION_TIMER_INTERVAL, motion_timer_expired)
			motion_timer.start()
		
		elif not GPIO.input(PIR_PIN):
			print("No motion detected.")
			
def detect_ldr(client):
	if auto_mode:
		if GPIO.input(LDR_PIN) == 0:
			#print("No light detected!")
			GPIO.output(LEDS_PIN, GPIO.HIGH)
			payload = {
			'ldr': 'no_light',
			'timestamp': int(time.time())
			}
			client.publish(MQTT_TOPIC_LDR, json.dumps(payload))
			#print(f"Published no light detected : {json.dumps(payload)}")
			
		elif GPIO.input(LDR_PIN) == 1:
			#print("Light detected, turning LEDs OFF")
			GPIO.output(LEDS_PIN, GPIO.LOW)
			
def detect_flame(client):
	global flame_alert
	if GPIO.input(FLAME_SENSOR_PIN):
		if not flame_alert:
			print("Flame detected!")
			GPIO.setup(BUZZER_PIN, GPIO.OUT)
			GPIO.output(BUZZER_PIN, GPIO.LOW)
			payload = {
			'flame': 'detected',
			'timestamp': int(time.time())
			}
			client.publish(MQTT_TOPIC_FLAME, json.dumps(payload))
			print(f"Published flame detected: {json.dumps(payload)}")
			flame_alert = False
	
def detect_rain(client):
	if GPIO.input(RAIN_SENSOR_PIN) == 1:
		print("Rain detected!")
		payload = { 
		    'rain': 'detected',
		    'timestamp': int(time.time())
		}
		client.publish(MQTT_TOPIC_RAIN, json.dumps(payload))
		print(f"Published rain detected: {json.dumps(payload)}")
	
def close_windows():
	print("Closing windows with low speed")
	for pulse_width in range(SERVO_MIN, SERVO_MAX, 10):
		pi.set_servo_pulsewidth(SERVO_PIN, pulse_width)
		time.sleep(SPEED)
	pi.set_servo_pulsewidth(SERVO_PIN, 0)
	
def open_windows():
	print("Opening windows in low speed")
	for pulse_width in range(SERVO_MAX, SERVO_MIN, -10):
		pi.set_servo_pulsewidth(SERVO_PIN, pulse_width)
		time.sleep(SPEED)
	pi.set_servo_pulsewidth(SERVO_PIN, 0)
			
def periodic_publish(client):
	publish_sensor_data(client)
	# schedule the next temperature publish
	Timer(PUBLISH_INTERNVAL, periodic_publish, [client]).start()
	
def main():
	client = mqtt.Client()
	client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
	client.on_connect = on_connect
	client.on_message = on_message
	
	client.connect(MQTT_BROKER, MQTT_PORT, 60)
	client.loop_start()
	
	#Start periodic temperature publishing
	Timer(PUBLISH_INTERNVAL, periodic_publish, [client]).start()
	
	try:
		while True:
			humidity, temperature = read_sensor()
			if humidity is not None and temperature is not None:
				control_fan(humidity, temperature)
			detect_motion(client)
			detect_flame(client)
			detect_ldr(client)
			detect_rain(client)
			time.sleep(1)
			
	except KeyboardInterrupt:
		print("Script interrupted by user")
		
	finally:
		GPIO.cleanup()
		client.loop_stop()
		client.disconnect()
		
if __name__ == "__main__":
	main()
