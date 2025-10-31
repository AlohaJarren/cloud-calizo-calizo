# SlimToolkit notes for CS 530 HW3

Goal: produce jarrenx/hw3tiny:latest from your working small image to chase a very low compressed size on Docker Hub, while keeping hw3large and hw3small unchanged for grading.

This doc uses Git Bash on Windows to avoid path-conversion issues.

## Prereqs

- Docker Desktop running
- A working small image: jarrenx/hw3small:latest
  - Build it first from repo root:
    docker build -f hw3/Dockerfile.small -t jarrenx/hw3small .

## One-time Git Bash setup

In Git Bash, disable path conversion so the docker.sock mount is not rewritten:

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="\*"

## Create hw3tiny with SlimToolkit

This runs the SlimToolkit container against your local Docker daemon, slims hw3small, and tags the result as hw3tiny.

docker run --rm -it \
 --privileged \
 -v /var/run/docker.sock:/var/run/docker.sock \
 -v "$PWD":/work \
 --workdir /work \
 dslim/slim:latest \
 build \
 --target jarrenx/hw3small:latest \
 --tag jarrenx/hw3tiny:latest \
 --http-probe=true \
 --http-probe-ports 5000 \
 --preserve-path-file hw3/preserved-paths.txt

Notes:

- The http probe will visit the container on port 5000. If you want to exercise more endpoints, you can add:
  --http-probe-cmd "curl -fsS http://$HOST:$PORT/ || true" \
   --http-probe-cmd "curl -fsS http://$HOST:$PORT/songs || true"
- The preserve list keeps \*.dist-info metadata so Werkzeug and Flask can read their versions.

## Test locally

docker run --rm --name hw3tiny -p 8000:5000 jarrenx/hw3tiny:latest

# new terminal

curl -fsS http://localhost:8000/ | head

## Push and check compressed size

docker push jarrenx/hw3tiny:latest

# On Docker Hub -> your repo -> Tags, read the "Compressed size" field.

## Troubleshooting

- If you see "mkdir C:\\Program Files\\Git\\var: Access is denied", you forgot the MSYS_NO_PATHCONV step. Run the two export commands again in Git Bash.
- If the app fails with "PackageNotFoundError", add or adjust entries in hw3/preserved-paths.txt and re-run SlimToolkit.
- If http probing hangs, try " --http-probe=false " and then provide "--exec" commands per SlimToolkit docs, or reduce to a single probe port.

## Submission notes

- The HW3 rubric only requires hw3large and hw3small. hw3tiny is optional icing to show optimization effort.
- Hw3tiny is derived from the working hw3small build.
