#!/bin/bash
set -e

LAYER_NAME="numpy-layer"
PYTHON_VERSION="3.11"
ARCH="x86_64"
BUILD_DIR="numpy_layer_build"
ZIP_NAME="numpy_layer.zip"

echo "🧱 Creando layer de NumPy para Lambda..."

# Limpieza previa
rm -rf $BUILD_DIR $ZIP_NAME
mkdir -p $BUILD_DIR/python

# Usamos imagen de Amazon Linux compatible con Lambda para compilar NumPy
docker run --rm -v "$PWD/$BUILD_DIR:/mnt" amazonlinux:2023 bash -c "
  yum install -y python3${PYTHON_VERSION//.} python3${PYTHON_VERSION//.}-devel gcc zip &&
  python3.${PYTHON_VERSION#*.} -m ensurepip &&
  python3.${PYTHON_VERSION#*.} -m pip install numpy -t /mnt/python
"

# Empaquetar ZIP
cd $BUILD_DIR && zip -r9 ../$ZIP_NAME python > /dev/null && cd ..

echo "📦 ZIP generado: $ZIP_NAME"

# Subir y publicar el layer
echo "☁️ Subiendo y publicando Layer..."
aws lambda publish-layer-version \
  --layer-name "$LAYER_NAME" \
  --description "NumPy for Python $PYTHON_VERSION" \
  --zip-file "fileb://$ZIP_NAME" \
  --compatible-runtimes "python${PYTHON_VERSION}" \
  --compatible-architectures "$ARCH"
