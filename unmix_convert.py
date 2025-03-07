import scyjava
import numpy as np
import tifffile
import os
import logging
import argparse

# Set up Python logging to suppress DEBUG messages
logging.basicConfig(level=logging.INFO)

# Initialize Java with bioformats and set logging level to WARN
scyjava.config.endpoints.append('ome:formats-gpl:6.7.0')
scyjava.start_jvm()

# Import necessary Java classes
ImageReader = scyjava.jimport('loci.formats.ImageReader')
OMEXMLServiceImpl = scyjava.jimport('loci.formats.services.OMEXMLServiceImpl')
DynamicMetadataOptions = scyjava.jimport('loci.formats.in.DynamicMetadataOptions')
MetadataTools = scyjava.jimport('loci.formats.MetadataTools')

def extract_channel_names_from_qptiff(file_path):
    # Create a reader and configure with OMEXML metadata
    reader = ImageReader()
    service = OMEXMLServiceImpl()
    
    # Set metadata store with appropriate options
    metadata = service.createOMEXMLMetadata()
    reader.setMetadataStore(metadata)
    reader.setId(file_path)
    
    try:
        # Get channel count
        channel_count = reader.getSizeC()
        
        # Extract the metadata as a retrievable object
        meta_retrieve = service.asRetrieve(metadata)
        
        # Get channel names
        channel_names = []
        for i in range(channel_count):
            try:
                # Series 0 is typically the main image
                name = meta_retrieve.getChannelName(0, i)
                
                # If name is None or empty, use a default name
                if name is None or str(name) == "":
                    name = f"Channel {i+1}"
                
                channel_names.append(str(name))
            except Exception as e:
                print(f"Error getting name for channel {i}: {e}")
                channel_names.append(f"Channel {i+1}")
        
        return channel_names
    
    finally:
        # Close the reader
        reader.close()

def unmix_channels(file_path, output_path, unmix_coeff=0.3, unmixing_matrix_data=None):
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
        size_z = reader.getSizeZ()
        size_t = reader.getSizeT()
        pixel_type = reader.getPixelType()
        bytes_per_pixel = reader.getBitsPerPixel() // 8
        
        # Get channel count
        channel_count = reader.getSizeC()
        
        # Extract the metadata as a retrievable object
        meta_retrieve = service.asRetrieve(metadata)
        
        # Find the index of the 'Sample AF' channel
        af_channel_index = -1
        for i in range(channel_count):
            name = meta_retrieve.getChannelName(0, i)
            if name == 'Sample AF':
                af_channel_index = i
                break
        
        if af_channel_index == -1:
            print("Could not find 'Sample AF' channel!")
            return
        
        print(f"Found 'Sample AF' at channel index {af_channel_index}")
        
        # Read the 'Sample AF' channel data
        af_channel_data = reader.openBytes(af_channel_index)
        af_channel_data = np.frombuffer(af_channel_data, dtype=np.uint8).reshape((size_y, size_x))
        
        # Prepare the unmixed data array
        unmixed_data = np.zeros((channel_count, size_y, size_x), dtype=np.uint8)
        
        # Read all channel data into a single array
        all_channel_data = np.zeros((channel_count, size_y, size_x), dtype=np.uint8)
        for i in range(channel_count):
            channel_data = reader.openBytes(i)
            all_channel_data[i] = np.frombuffer(channel_data, dtype=np.uint8).reshape((size_y, size_x))
        
        unmixed_channel_names = []
        
        # Apply unmixing matrix if provided
        if unmixing_matrix_data is not None:
            unmixing_matrix = unmixing_matrix_data['unmixing_matrix']
            unmixing_channel_names = unmixing_matrix_data['channel_names']
            
            # Match channels between the image and the unmixing matrix
            channel_indices = []
            for name in unmixing_channel_names:
                if name in meta_retrieve.getChannelName(0, i):
                    channel_indices.append(meta_retrieve.getChannelName(0, i).index(name))
                else:
                    channel_indices.append(-1)
            
            # Filter out channels that are not found in the image
            valid_indices = [i for i in channel_indices if i != -1]
            unmixing_matrix = unmixing_matrix[:, valid_indices]
            all_channel_data = all_channel_data[valid_indices]
            
            # Flatten the channel data for matrix multiplication
            flat_channel_data = all_channel_data.reshape(len(valid_indices), -1)
            unmixed_flat_data = np.dot(unmixing_matrix, flat_channel_data)
            unmixed_data[:unmixing_matrix.shape[0]] = unmixed_flat_data.reshape(unmixing_matrix.shape[0], size_y, size_x)
            
            # Copy any remaining channels that were not unmixed
            if unmixing_matrix.shape[0] < channel_count:
                unmixed_data[unmixing_matrix.shape[0]:] = all_channel_data[unmixing_matrix.shape[0]:]
            
            # Add channel names for unmixed channels
            for i in range(unmixing_matrix.shape[0]):
                unmixed_channel_names.append(unmixing_channel_names[i])
            
            # Add channel names for remaining channels
            for i in range(unmixing_matrix.shape[0], channel_count):
                unmixed_channel_names.append(meta_retrieve.getChannelName(0, i))
        else:
            # Default unmixing by subtracting AF channel
            unmixed_channel_index = 0
            for i in range(channel_count):
                if i != af_channel_index:
                    unmixed_data[unmixed_channel_index] = np.maximum(0, all_channel_data[i] - (af_channel_data * unmix_coeff))
                    unmixed_channel_names.append(meta_retrieve.getChannelName(0, i))
                    unmixed_channel_index += 1
        
        # Save the unmixed data to a new OME-TIFF file using tifffile
        metadata = {
            'axes': 'CYX',
            'Channel': {'Name': unmixed_channel_names}
        }
        tifffile.imwrite(output_path, unmixed_data, photometric='minisblack', metadata=metadata)
        
        print(f"Unmixed data saved to {output_path}")
        
    finally:
        # Close the reader
        reader.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unmix channels in a QPTIFF file and save to OME-TIFF.")
    parser.add_argument("input", help="Path to the input QPTIFF file")
    parser.add_argument("output", help="Path to the output OME-TIFF file")
    parser.add_argument("--unmixing_matrix", help="Path to the unmixing matrix .npy file", default=None)
    args = parser.parse_args()

    # Load unmixing matrix if provided
    unmixing_matrix_data = None
    if args.unmixing_matrix:
        unmixing_matrix_data = np.load(args.unmixing_matrix, allow_pickle=True).item()

    # Perform unmixing and save to OME-TIFF
    unmix_channels(args.input, args.output, unmixing_matrix_data=unmixing_matrix_data)

