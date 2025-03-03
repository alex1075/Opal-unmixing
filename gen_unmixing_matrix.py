import scyjava
import numpy as np
import os
import logging
import argparse
from glob import glob

# Set up Python logging to suppress DEBUG messages
logging.basicConfig(level=logging.INFO)

# Initialize Java with bioformats and set logging level to WARN
scyjava.config.endpoints.append('ome:formats-gpl:6.7.0')
scyjava.start_jvm()

# Import necessary Java classes
ImageReader = scyjava.jimport('loci.formats.ImageReader')
OMEXMLServiceImpl = scyjava.jimport('loci.formats.services.OMEXMLServiceImpl')

def read_single_stain(file_path, unmix_coeff=0.3):
    # Create a reader and configure with OMEXML metadata
    reader = ImageReader()
    service = OMEXMLServiceImpl()
    
    # Set metadata store with appropriate options
    metadata = service.createOMEXMLMetadata()
    reader.setMetadataStore(metadata)
    reader.setId(file_path)
    
    try:
        # Get image dimensions
        size_x = reader.getSizeX()
        size_y = reader.getSizeY()
        channel_count = reader.getSizeC()
        
        # Extract the metadata as a retrievable object
        meta_retrieve = service.asRetrieve(metadata)
        
        # Find the indices of the 'Sample AF' and 'DAPI' channels
        af_channel_index = -1
        dapi_channel_index = -1
        for i in range(channel_count):
            name = meta_retrieve.getChannelName(0, i)
            if name == 'Sample AF':
                af_channel_index = i
            elif name == 'DAPI':
                dapi_channel_index = i
        
        if af_channel_index == -1:
            print("Could not find 'Sample AF' channel!")
            return None
        
        # Read the 'Sample AF' channel data
        af_channel_data = reader.openBytes(af_channel_index)
        af_channel_data = np.frombuffer(af_channel_data, dtype=np.uint8).reshape((size_y, size_x))
        
        # Read and unmix the other channels
        channel_data = []
        for i in range(channel_count):
            if i != af_channel_index and (i != dapi_channel_index or channel_count == 2):
                data = reader.openBytes(i)
                data = np.frombuffer(data, dtype=np.uint8).reshape((size_y, size_x))
                unmixed_data = np.maximum(0, data - (af_channel_data * unmix_coeff))
                channel_data.append(unmixed_data)
        
        return np.array(channel_data)
    
    finally:
        # Close the reader
        reader.close()

def generate_unmixing_matrix(single_stain_folder):
    # Get list of single stain QPTIFF files
    file_paths = glob(os.path.join(single_stain_folder, "*.qptiff"))
    
    if not file_paths:
        print("No QPTIFF files found in the specified folder.")
        return
    
    # Read the single stain images
    single_stain_images = [read_single_stain(file_path) for file_path in file_paths]
    
    # Filter out any None values (in case 'Sample AF' channel was not found)
    single_stain_images = [img for img in single_stain_images if img is not None]
    
    if not single_stain_images:
        print("No valid single stain images found.")
        return
    
    # Stack the images to form a 3D array (stains x channels x pixels)
    single_stain_images = np.stack(single_stain_images, axis=0)
    
    # Reshape the array to (stains x channels x pixels)
    stains, channels, height, width = single_stain_images.shape
    single_stain_images = single_stain_images.reshape(stains, channels, -1)
    
    # Compute the unmixing matrix
    unmixing_matrix = np.linalg.pinv(single_stain_images)
    
    return unmixing_matrix

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an unmixing matrix from single stain QPTIFF files.")
    parser.add_argument("single_stain_folder", help="Path to the folder containing single stain QPTIFF files")
    parser.add_argument("output", help="Path to the output file to save the unmixing matrix")
    args = parser.parse_args()
    
    # Generate the unmixing matrix
    unmixing_matrix = generate_unmixing_matrix(args.single_stain_folder)
    
    if unmixing_matrix is not None:
        # Save the unmixing matrix to a file
        np.save(args.output, unmixing_matrix)
        print(f"Unmixing matrix saved to {args.output}")