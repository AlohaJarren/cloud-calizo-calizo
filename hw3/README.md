# Dockerized Songs MVP

Two images built from repo root:

- hw3large: Ubuntu 22.04 base
- hw3small: Alpine base, multi-stage, trimmed

The app is launched by hw3/start.py so we do not edit hw2 code. It binds 0.0.0.0:5000 inside the container.

## Build (from repo root so hw2/ is in context)

docker build -f hw3/Dockerfile.large -t <dockerhub_id>/hw3large .
docker build -f hw3/Dockerfile.small -t <dockerhub_id>/hw3small .

## Quick local run

docker run --name hw3large -p 8000:5000 --rm <dockerhub_id>/hw3large

# new terminal

wget -qO landing_large.html http://localhost:8000/
cat landing_large.html

docker run --name hw3small -p 8000:5000 --rm <dockerhub_id>/hw3small

# new terminal

wget -qO landing_small.html http://localhost:8000/
cat landing_small.html

## Push to Docker Hub

docker login
docker push <dockerhub_id>/hw3large
docker push <dockerhub_id>/hw3small

## Prune on the Ubuntu VM, then pull-run from Hub (for screenshots)

# stop and remove any containers

docker ps -a
docker stop hw3large hw3small || true
docker rm hw3large hw3small || true

# remove all local images so the pull is visible

docker rmi -f $(docker images -q) || true

# run from Hub and show layer pulls

docker run --name hw3large -p 8000:5000 --rm <dockerhub_id>/hw3large

# in a second terminal

wget -qO vm_large.html http://localhost:8000/
cat vm_large.html

docker run --name hw3small -p 8000:5000 --rm <dockerhub_id>/hw3small

# in a second terminal

wget -qO vm_small.html http://localhost:8000/
cat vm_small.html

## Screenshot checklist (place in a Google Doc, then export to hw3/screenshots.pdf)

1. Docker Hub -> Repositories -> <dockerhub_id>/hw3large -> Tags page showing compressed size
2. Docker Hub -> Repositories -> <dockerhub_id>/hw3small -> Tags page showing compressed size
3. Terminal after pruning images (docker rmi output visible)
4. Terminal showing docker run pulling layers for hw3large from Hub
5. Terminal showing wget http://localhost:8000 and cat of vm_large.html contents
6. Terminal showing docker run pulling layers for hw3small from Hub
7. Terminal showing wget http://localhost:8000 and cat of vm_small.html contents

## Notes

- Build context: use repo root with -f hw3/... so the Docker build sees hw2/.
- Port mapping: host 8000 -> container 5000 as required by the assignment.
- Non-root runtime: both images drop to a non-root user after setup.
- Healthcheck: each image returns 200 at / if the app is healthy.

## Alternate build path (if you prefer being inside hw3/)

cd hw3
docker build -f Dockerfile.large -t <dockerhub_id>/hw3large ..
docker build -f Dockerfile.small -t <dockerhub_id>/hw3small ..

## Troubleshooting tips

- If docker is not found on your host, install Docker Desktop on Windows or Docker Engine on the Ubuntu VM.
- If Alpine warns about PEP 668, the small image already installs as root and then drops to appuser.
- If wget is missing on your VM, sudo apt-get install -y wget.

## Final submission

- Export your Google Doc with screenshots to hw3/screenshots.pdf
- git add hw3/screenshots.pdf
- git commit -m "hw3: add screenshots.pdf"
- git push
