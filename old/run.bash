

echo "RUN=================="
echo "RUN=================="
echo "RUN=================="
echo "RUN=================="
echo "RUN=================="



# xhost +local:
xhost +
docker run --rm \
  --platform=linux/amd64 \
  -e POLARS_SKIP_CPU_CHECK=1 \
  -e DISPLAY=host.docker.internal:0 \
  -v "$(pwd):/app" \
  -v $(pwd)/data:/app/data \
  redline python3 /app/data_module.py


xhost -

echo "DONE=================="
echo "DONE=================="
echo "DONE=================="
echo "DONE=================="
echo "DONE=================="

