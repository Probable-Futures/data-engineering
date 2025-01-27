FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies
RUN yum install -y gcc libpq-devel

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t .

COPY . .

# Command for the Lambda runtime
CMD ["lambda_function.lambda_handler"]
