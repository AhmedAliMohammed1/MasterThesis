# Optional memory probe for the existing TensorRT10 diagnostic adapter.
FROM pp-infer:reference-trt10
RUN apt-get update && apt-get install -y --no-install-recommends cuda-sanitizer-12-9=12.9.79-1 && rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/local/cuda-12.9/compute-sanitizer:${PATH}
