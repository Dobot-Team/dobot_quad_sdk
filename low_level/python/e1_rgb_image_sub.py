import dds_middleware_python as dds
import time
import os
import cv2
import numpy as np


def image_callback(data):
    print("Received RGB CompressedImage:")
    print(
        f"  Timestamp: {data.header().stamp().sec()}.{data.header().stamp().nanosec():09d} (sec.nanosec)"
    )
    print(f"  Frame ID: {data.header().frame_id()}")
    print(f"  Format: {data.format()}")
    print(f"  Data size: {len(data.data())} bytes")

    # Convert data to numpy array
    np_arr = np.array(data.data(), dtype=np.uint8)

    # Decode image
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is not None:
        # Generate filename
        filename = f"rgb_images/rgb_{data.header().stamp().sec()}_{data.header().stamp().nanosec()}.png"

        # Save image
        cv2.imwrite(filename, image)
        print(f"Saved raw image to {filename}")
    else:
        print("Failed to decode image!")

    print("---")


def main():
    # Create save directory
    os.makedirs("rgb_images", exist_ok=True)

    middleware = dds.PyDDSMiddleware("config/dds_config.yaml")

    middleware.subscribeCompressedImage("rt/camera/camera2/image_compressed", image_callback)

    print("Subscribed to RGB image topic. Waiting for messages...")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
