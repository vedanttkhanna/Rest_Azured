FROM public.ecr.aws/lambda/python:3.12
# rasterio's bundled GDAL needs libexpat, which the minimal Lambda base image lacks (ImportError at handler import).
RUN dnf install -y expat && dnf clean all
COPY solar/requirements.lock.txt /var/task/requirements.txt
RUN pip install --no-cache-dir -r /var/task/requirements.txt
COPY solar/solar /var/task/solar
COPY solar/handlers.py /var/task/handlers.py
COPY contracts/schemas /var/task/contracts/schemas
ENV PYTHONUNBUFFERED=1
CMD ["handlers.simulate_handler"]
