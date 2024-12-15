# Use Alpine base image for smaller size
FROM python:3.9-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Make port 5000 available to the world outside the container
EXPOSE 5000

# Define environment variable (optional for Flask)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Use python -m flask to run the app
# CMD ["python", "-m", "flask", "run"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]