# Base image
FROM amazonlinux:2

RUN yum groupinstall -y "Development Tools" && \
    yum install -y gcc gcc-c++ make curl tar gzip wget \
            libjpeg-devel libpng-devel libtiff-devel \
            geos geos-devel sqlite sqlite-devel \
            proj proj-devel zlib zlib-devel libproj-dev \
            libpq-dev

RUN amazon-linux-extras enable postgresql13 && \
    yum install -y postgresql postgresql-devel
            
# Install SQLite from source
RUN curl -LO https://www.sqlite.org/2023/sqlite-autoconf-3420000.tar.gz && \
    tar -xzvf sqlite-autoconf-3420000.tar.gz && \
    cd sqlite-autoconf-3420000 && \
    CFLAGS="-DSQLITE_ENABLE_COLUMN_METADATA=1" \
    ./configure && make && make install && \
    cd .. && rm -rf sqlite-autoconf-3420000 sqlite-autoconf-3420000.tar.gz

RUN sqlite3 --version

# Set environment variables 
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH
ENV PATH="/usr/bin:$PATH"
ENV LD_LIBRARY_PATH=/usr/lib64:$LD_LIBRARY_PATH
ENV AWS_LAMBDA_FUNCTION_HANDLER=app.lambda_handler

RUN curl -LO https://download.osgeo.org/proj/proj-6.3.2.tar.gz && \
    tar -xzvf proj-6.3.2.tar.gz && \
    cd proj-6.3.2 && \
    SQLITE3_CFLAGS="-I/usr/local/include" SQLITE3_LIBS="-L/usr/local/lib -lsqlite3" \
    ./configure && make && make install && \
    cd .. && rm -rf proj-6.3.2 proj-6.3.2.tar.gz

# Download and build GDAL
RUN curl -LO http://download.osgeo.org/gdal/3.4.1/gdal-3.4.1.tar.gz && \
    tar -xzvf gdal-3.4.1.tar.gz && \
    cd gdal-3.4.1 && \
    PKG_CONFIG_PATH=/usr/lib64 \
    ./configure --with-pg-config=/usr/bin/pg_config --with-proj=/usr/local --with-pg=yes && \
    make && make install && \
    cd .. && rm -rf gdal-3.4.1 gdal-3.4.1.tar.gz

# Install AWS Lambda Runtime Interface Client
RUN yum install -y python3-pip
RUN pip3 install awslambdaric boto3

# Verify GDAL installation
RUN ogr2ogr --version
RUN ogrinfo --formats

# Set working directory
WORKDIR /var/task

# Copy the project files
COPY . .

# Install Makefile and dependencies
RUN chmod +x /var/task/Makefile

# ARG ENV=dev
# COPY .env.$ENV .env

# # Source the .env file to load environment variables during build
# RUN bash -c "source .env && env > /etc/environment"

# Commands for AWS Lambda
ENTRYPOINT [ "python3", "-m", "awslambdaric" ]

CMD ["app.lambda_handler"]

