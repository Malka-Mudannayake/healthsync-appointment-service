
## Run Server

```python app.py```


## Setup Environemnt

```python -m venv venv```

## Active Env
```venv\Scripts\activate```

## Install Dependencies
``` pip install -r requirements.txt```

## Build Docker Image

```docker build -t healthsync/appointment-service .```


```docker rm appointment-service-container```



aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 443370721662.dkr.ecr.ap-southeast-1.amazonaws.com


docker build -t healthsync/appointment-service .


docker tag healthsync/appointment-service:latest 443370721662.dkr.ecr.ap-southeast-1.amazonaws.com/healthsync/appointment-service:latest


docker push 443370721662.dkr.ecr.ap-southeast-1.amazonaws.com/healthsync/appointment-service:latest







