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

def read_single_stain(file_path):
    # Create a reader and configure with OMEXML metadata
    reader = ImageReader()
    service = OMEXMLServiceImpl()
    
    # Set metadata store with appropriate options
    metadata = service.createOMEXMLMetadata()
    reader.setMetadataStore(metadata)
    reader.setId(file_path)
    
    try:
        # Get image dimensions and pixel type
        size_x = reader.getSizeX()
        size_y = reader.getSizeY()
        channel_count = reader.getSizeC()
        pixel_type = reader.getPixelType()
        bytes_per_pixel = reader.getBitsPerPixel() // 8
        
        # Determine the numpy data type based on the pixel type
        if pixel_type == 0:  # UINT8
            dtype = np.uint8
        elif pixel_type == 1:  # INT8
            dtype = np.int8
        elif pixel_type == 2:  # UINT16
            dtype = np.uint16
        elif pixel_type == 3:  # INT16
            dtype = np.int16
        elif pixel_type == 4:  # UINT32
            dtype = np.uint32
        elif pixel_type == 5:  # INT32
            dtype = np.int32
        elif pixel_type == 6:  # FLOAT
            dtype = np.float32
        elif pixel_type == 7:  # DOUBLE
            dtype = np.float64
        else:
            raise ValueError(f"Unsupported pixel type: {pixel_type}")
        
        # Extract the metadata as a retrievable object
        meta_retrieve = service.asRetrieve(metadata)
        
        # Determine if the file is an IM3 file
        is_im3 = file_path.lower().endswith('.im3')
        
        # Find the indices of the 'Sample AF' and 'DAPI' channels
        af_channel_index = -1
        dapi_channel_index = -1
        for i in range(channel_count):
            name = meta_retrieve.getChannelName(0, i)
            if name == 'Sample AF' and not is_im3:
                af_channel_index = i
            elif name == 'DAPI':
                dapi_channel_index = i
        
        if af_channel_index == -1 and not is_im3:
            print(f"Could not find 'Sample AF' channel in {file_path}. Proceeding without it.")
        
        # Read the 'Sample AF' channel data if available
        af_channel_data = None
        if af_channel_index != -1:
            af_channel_data = reader.openBytes(af_channel_index)
            af_channel_data = np.frombuffer(af_channel_data, dtype=dtype).reshape((size_y, size_x))
        
        # Read the other channels
        channel_data = []
        channel_names = []
        for i in range(channel_count):
            if i != af_channel_index and (i != dapi_channel_index or channel_count == 2):
                data = reader.openBytes(i)
                data = np.frombuffer(data, dtype=dtype).reshape((size_y, size_x))
                channel_data.append(data)
                channel_names.append(meta_retrieve.getChannelName(0, i))
        
        return np.array(channel_data), channel_names
    
    finally:
        # Close the reader
        reader.close()

def generate_unmixing_matrix(single_stain_folder, batch_size=10):
    # Get list of single stain IM3 and QPTIFF files
    file_paths = glob(os.path.join(single_stain_folder, "*.im3")) + glob(os.path.join(single_stain_folder, "*.qptiff"))
    
    if not file_paths:
        print("No IM3 or QPTIFF files found in the specified folder.")
        return
    
    # Initialize the unmixing matrix
    unmixing_matrix = None
    
    # Read the single stain images in batches
    single_stain_images = []
    channel_names = []
    for i, file_path in enumerate(file_paths):
        img, names = read_single_stain(file_path)
        if img is not None:
            single_stain_images.append(img)
            channel_names.extend(names)
        
        # Process the batch
        if (i + 1) % batch_size == 0 or (i + 1) == len(file_paths):
            # Flatten the images to create a matrix where each row represents a pixel and each column represents a channel
            single_stain_matrix = np.concatenate([img.reshape(img.shape[0], -1).T for img in single_stain_images], axis=0)
            
            # Use memory mapping to handle large arrays
            mm = np.memmap('single_stain_matrix.dat', dtype=single_stain_matrix.dtype, mode='w+', shape=single_stain_matrix.shape)
            mm[:] = single_stain_matrix[:]
            
            # Compute the pseudoinverse of the single stain matrix
            pinv_matrix = np.linalg.pinv(mm)
            
            # Initialize or update the unmixing matrix
            if unmixing_matrix is None:
                unmixing_matrix = pinv_matrix
            else:
                unmixing_matrix += pinv_matrix
            
            # Clean up the memory-mapped file
            del mm
            os.remove('single_stain_matrix.dat')
            
            # Clear the batch
            single_stain_images = []
    
    return unmixing_matrix, channel_names

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an unmixing matrix from single stain IM3 or QPTIFF files.")
    parser.add_argument("single_stain_folder", help="Path to the folder containing single stain IM3 or QPTIFF files")
    parser.add_argument("output", help="Path to the output file to save the unmixing matrix")
    args = parser.parse_args()
    
    # Generate the unmixing matrix
    unmixing_matrix, channel_names = generate_unmixing_matrix(args.single_stain_folder)
    
    if unmixing_matrix is not None:
        # Save the unmixing matrix and channel names to a file
        np.save(args.output, {'unmixing_matrix': unmixing_matrix, 'channel_names': channel_names})
        print(f"Unmixing matrix and channel names saved to {args.output}")