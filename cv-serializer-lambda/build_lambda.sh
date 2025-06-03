#!/bin/bash
set -e

# Configuración
PYTHON_VERSION="3.11"
LAMBDA_IMAGE="amazonlinux:2023"
ZIP_NAME="deployment.zip"
CONTAINER_NAME="lambda-build-container"
BUILD_DIR=".lambda_build"
LAMBDA_NAME="cvserializer"
S3_BUCKET="bucketfordeployingmylambdafnction"

echo "🔧 Preparando build para AWS Lambda con Python $PYTHON_VERSION..."

# Limpieza previa
rm -rf "$BUILD_DIR" "$ZIP_NAME"
mkdir -p "$BUILD_DIR"

# Copiar archivos fuente
cp lambda_function.py requirements.txt "$BUILD_DIR/"
cp app.py "$BUILD_DIR/" 2>/dev/null || true

# Crear Dockerfile temporal
cat > "$BUILD_DIR/Dockerfile" <<EOF
FROM amazonlinux:2023

# Instalar Python y herramientas necesarias
RUN yum -y install \
    python3.11 \
    python3.11-devel \
    python3.11-pip \
    gcc \
    zip \
    git \
    && yum clean all

WORKDIR /app
COPY . .

RUN python3.11 -m pip install --upgrade pip \
 && python3.11 -m pip install --no-cache-dir -r requirements.txt -t package \
 && find package/numpy -type d -name '__pycache__' -exec rm -r {} + \
 && find package/numpy -type f -name '*.c' -delete \
 && cp lambda_function.py package/ \
 && if [ -f app.py ]; then cp app.py package/; fi \
 && cd package && zip -r9 /app/deployment.zip .

EOF

# Build Docker image
docker build -f "$BUILD_DIR/Dockerfile" -t lambda-zip-build "$BUILD_DIR"

# Crear contenedor temporal y extraer el ZIP
docker create --name $CONTAINER_NAME lambda-zip-build
docker cp $CONTAINER_NAME:/app/$ZIP_NAME .
docker rm $CONTAINER_NAME

echo "✅ ZIP $ZIP_NAME generado exitosamente."

# Subir a S3
echo "☁️ Subiendo a S3..."
aws s3 cp $ZIP_NAME s3://$S3_BUCKET/

# Actualizar Lambda
echo "🔄 Actualizando Lambda $LAMBDA_NAME..."
aws lambda update-function-code \
  --function-name $LAMBDA_NAME \
  --s3-bucket $S3_BUCKET \
  --s3-key $ZIP_NAME

echo "✅ Despliegue completo."
