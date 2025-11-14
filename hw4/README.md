# CS 530 - HW4: Cloud Run + Cloud Datastore

This homework adapts the HW2 Flask app to use Cloud Datastore, packages it in a container, and deploys it to Cloud Run under the service name `hw4`.

## Quick map

- Storage: Cloud Datastore (Kind: `CS530_SongsHW4`, Namespace: `cs530-hw4`)
- App routes: `/`, `/songs`, `/songs/new`, `POST /songs`, `/healthz`, `/readyz`
- Service name on Cloud Run: `hw4`
- URL recorded in: `hw4/url.txt`

## Local run

```bash
gcloud auth application-default login   # local ADC for Datastore

export PROJECT_ID=YOUR_PROJECT_ID
export DATASTORE_NAMESPACE=cs530-hw4
export DATASTORE_KIND=CS530_SongsHW4
export SECRET_KEY=placeholder

python hw4/app.py
# open http://localhost:5000
# try /healthz and /readyz too
```
