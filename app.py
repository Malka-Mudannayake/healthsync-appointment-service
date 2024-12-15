from flask import Flask, request, jsonify
import boto3
from botocore.exceptions import ClientError
import uuid
import logging
from datetime import datetime
import requests

# Notification Service URL
NOTIFICATION_SERVICE_URL = 'http://notification-service:82/notification/send-notification'
# NOTIFICATION_SERVICE_URL = 'http://localhost:5001/notification/send-notification'

# Initialize Flask app
app = Flask(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='ap-southeast-1')
appointment_table = dynamodb.Table('appointments')
booking_table = dynamodb.Table('bookings')

def configure_logging():
    # Remove default Flask handlers
    app.logger.handlers.clear()
    
    # Set the log level to DEBUG for both dev and prod environments
    app.logger.setLevel(logging.DEBUG)

    # Create a console handler to display logs in the terminal
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Set the format for the log messages
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    # Add the console handler to Flask's default logger
    app.logger.addHandler(console_handler)

@app.before_request
def log_request():
    app.logger.info(f"Incoming Request: {request.method} {request.url}")
    
# Call configure_logging during app setup
configure_logging()


# Check if the table exists, if not create it
def create_appointment_table_if_not_exists():
    try:
        # Check if the table already exists
        appointment_table.load()
        app.logger.info("appointment_table connected ...... appointment-service")
    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        # Table doesn't exist, create it
        app.logger.info("Table does not exist. Creating new table...")
        table = dynamodb.create_table(
            TableName='appointments',
            KeySchema=[
                {
                    'AttributeName': 'appointment_id',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'appointment_id',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.meta.client.get_waiter('table_exists').wait(TableName='appointments')
        app.logger.info("Appointment Table created successfully.")
        
def create_booking_table_if_not_exists():
    try:
        # Check if the table already exists
        booking_table.load()
        app.logger.info("booking_table connected ...... appointment-service")
    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        # Table doesn't exist, create it
        app.logger.info("Table does not exist. Creating new table...")
        table = dynamodb.create_table(
            TableName='bookings',
            KeySchema=[
                {
                    'AttributeName': 'booking_id',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'booking_id',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.meta.client.get_waiter('table_exists').wait(TableName='bookings')
        app.logger.info("Booking Table created successfully.")

# Initialize the table on app startup
create_appointment_table_if_not_exists()
create_booking_table_if_not_exists()

# Method to check if DynamoDB connection is working
@app.route('/db-check', methods=['GET'])
def check_db_connection():
    try:
        # Attempt to list tables to check if connection works
        tables = dynamodb.tables.all()
        table_names = [table.name for table in tables]
        return jsonify({"status": "success", "message": "Connected to DynamoDB", "tables": table_names}), 200
    except ClientError as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 1. Doctor Creates Appointment with Max Patient Count
@app.route('/appointment/create-appointment', methods=['POST'])
def create_appointment():
    
    try:
        data = request.json
        if data is None:
            app.logger.info("Appointment data not found!")
            return jsonify({'error': 'invalid data'}), 400
            
        doctor_id = data['doctor_id']
        appointment_data = data['appointment_data']
        
        appointment_id = str(uuid.uuid4())
        appointment_data['appointment_id'] = appointment_id
        appointment_data['doctor_id'] = doctor_id
        appointment_data['created_at'] = datetime.utcnow().isoformat()
        
        # Set max patient count for the appointment
        # Default max 5 patients
        appointment_data['max_patient_count'] = appointment_data.get('max_patient_count', 5)  
        
        appointment_table.put_item(Item=appointment_data)
        app.logger.info("Appointment created successfully!")

        # Send Notification to all patients about the appointment availability
        # Send only once, when the appointment is created
        notification_data = {
            'recipient_id': doctor_id,
            'recipient_type': 'doctor',
            'message': f"Dr. {doctor_id}, your appointment has been created for {appointment_data['appointment_time']}. You can now start receiving patients."
        }

        response = requests.post(NOTIFICATION_SERVICE_URL, json=notification_data)
        if response.status_code == 200:
            app.logger.info("Notification sent to doctor!")
        else:
            app.logger.info(f"Failed to send notification: {response.text}")
        
        return jsonify({'message': 'Appointment information saved successfully', 'appointment_id': appointment_id}), 200
        
    except Exception as e:
        app.logger.info(f"Error creating  Appointment: {str(e)}")
        return jsonify({'error': str(e)}), 400


# 2. Patient Books Appointment (Check Max Count)
@app.route('/appointment/book-appointment', methods=['POST'])
def book_appointment():
    
    try:
        data = request.json 
        if data is None:
            app.logger.info("booking data not found!")
            return jsonify({'error': 'invalid data'}), 400
        
        appointment_id  = data['appointment_id']
        patient_id = data['patient_id']
        
        # Check the current number of bookings for the appointment
        response = booking_table.scan(
            FilterExpression="appointment_id = :appointment_id",
            ExpressionAttributeValues={':appointment_id': appointment_id}
        )
        
        current_booking_count = len(response['Items'])
        
        # Get max patient count from Appointment table
        appointment_response = appointment_table.get_item(Key={'appointment_id': appointment_id})
        max_patient_count = appointment_response.get('Item', {}).get('max_patient_count', 5)

        if current_booking_count >= max_patient_count:
            app.logger.info(f"Cannot book appointment. Maximum patient count of {max_patient_count} reached.")
            return jsonify('Cannot book appointment. Maximum patient count exceeded!'), 400
            return

        # Create the booking for the patient
        booking_id = str(uuid.uuid4())
        booking_data = {
            'booking_id': booking_id,
            'appointment_id': appointment_id,
            'patient_id': patient_id,
            'status': 'BOOKED',
            'created_at': datetime.utcnow().isoformat(),
            'prescription': None,  # Initially, prescription is empty
            'diagnosis': None  # Initially, prescription is empty
        }

        booking_table.put_item(Item=booking_data)
        app.logger.info("Appointment booked successfully for the patient!")

        # Send Notification to Patient
        notification_data = {
            'recipient_id': patient_id,
            'recipient_type': 'patient',
            'message': f"Your appointment for {appointment_id} has been booked successfully."
        }

        response = requests.post(NOTIFICATION_SERVICE_URL, json=notification_data)
        if response.status_code == 200:
            app.logger.info("Notification sent to patient!")
        else:
            app.logger.info(f"Failed to send notification: {response.text}")
        
        return jsonify({'message': 'Booking information saved successfully', 'booking_id': booking_id}), 200
    
    except Exception as e:
        app.logger.info(f"Error Booking Appointment: {str(e)}")
        return jsonify({'error': str(e)}), 400


# Update Prescription for a Patient (When Doctor Adds Prescription)
@app.route('/appointment/update-booking', methods=['POST'])
def update_prescription():
    try:
        data = request.json 
        if data is None:
            app.logger.info("booking data not found!")
            return jsonify({'error': 'invalid data'}), 400
        
        booking_id = data['booking_id']
        prescription_data = data['prescription_data']
        diagnosis = data['diagnosis']
        status = 'COMPLETED'
        
        booking_table.update_item(
            Key={'booking_id': booking_id},
            ExpressionAttributeNames={
                '#status': 'status' 
            },
            UpdateExpression="SET prescription = :prescription, diagnosis = :diagnosis, #status = :channel_status",
            ExpressionAttributeValues={':prescription': prescription_data, ':diagnosis': diagnosis, ':channel_status': status}
        )
        app.logger.info("Prescription updated for the patient!")
        
        return jsonify({'message': 'Prescription updated for the patient!'}), 200
    
    except Exception as e:
        app.logger.info(f"Error Updating Booking Data: {str(e)}")
        return jsonify({'error': str(e)}), 400


@app.route('/appointment/with-bookings', methods=['POST'])
def get_appointment_with_bookings():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'data is required'}), 400
        
        appointment_id = data['appointment_id']

        # Fetch the appointment by appointment_id
        appointment_response = appointment_table.get_item(Key={'appointment_id': appointment_id})
        appointment = appointment_response.get('Item')

        if not appointment:
            return jsonify({'message': 'Appointment not found'}), 404

        # Fetch related bookings for the appointment
        booking_response = booking_table.scan(
            FilterExpression="appointment_id = :appointment_id",
            ExpressionAttributeValues={':appointment_id': appointment_id}
        )
        bookings = booking_response.get('Items', [])

        # Combine appointment with its bookings
        result = {
            'appointment': appointment,
            'bookings': bookings
        }

        return jsonify(result), 200

    except Exception as e:
        app.logger.info(f"Error Fetching Appointment with Bookings: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/appointment/filter-by-bookings', methods=['POST'])
def filter_appointments_by_bookings():
    try:
        data = request.json
        if data is None:
            app.logger.info("Filter criteria not provided!")
            return jsonify({'error': 'Invalid filter criteria'}), 400

        # Example filter criteria from the request body
        patient_id = data.get('patient_id')

        # Build the FilterExpression for bookings
        filter_expression = []
        expression_attribute_values = {}

        if patient_id:
            filter_expression.append("patient_id = :patient_id")
            expression_attribute_values[':patient_id'] = patient_id
        
        # Combine expressions
        final_filter_expression = " AND ".join(filter_expression)

        # Query bookings table with the filter
        response = booking_table.scan(
            FilterExpression=final_filter_expression,
            ExpressionAttributeValues=expression_attribute_values,
        )

        bookings = response.get('Items', [])
        if not bookings:
            return jsonify({'message': 'No bookings found for the given criteria'}), 404

        # Extract appointment IDs from bookings
        appointment_ids = list(set(booking['appointment_id'] for booking in bookings))

        # Fetch appointments by IDs
        appointments = []
        for appointment_id in appointment_ids:
            appointment_response = appointment_table.get_item(Key={'appointment_id': appointment_id})
            if 'Item' in appointment_response:
                appointments.append(appointment_response['Item'])

        if not appointments:
            return jsonify({'message': 'No appointments found for the related bookings'}), 404

        return jsonify({'appointments': appointments}), 200

    except Exception as e:
        app.logger.info(f"Error Filtering Appointments: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Main Route
@app.route('/')
def home():
    return f"Appointment Service"


# Main Function
if __name__ == '__main__':
    app.logger.info("appointment-service started")
    app.run(debug=False)
