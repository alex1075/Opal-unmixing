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
ImageWriter = scyjava.jimport('loci.formats.ImageWriter')

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

def convert_to_ometiff(input_file, output_file):
    """
    Converts a supported file (e.g., .qptiff, .im3) to OME-TIFF format.
    """
    reader = ImageReader()
    writer = ImageWriter()
    service = OMEXMLServiceImpl()
    
    metadata = service.createOMEXMLMetadata()
    reader.setMetadataStore(metadata)
    reader.setId(input_file)
    
    writer.setMetadataRetrieve(metadata)
    writer.setId(output_file)
    
    try:
        for series in range(reader.getSeriesCount()):
            reader.setSeries(series)
            writer.setSeries(series)
            for plane in range(reader.getImageCount()):
                img = reader.openBytes(plane)
                writer.saveBytes(plane, img)
        print(f"Converted {input_file} to {output_file}")
    except Exception as e:
        print(f"Error converting {input_file} to {output_file}: {e}")
    finally:
        reader.close()
        writer.close()

def process_folder(input_folder, output_folder):
    """
    Processes all .qptiff and .im3 files in the input folder and converts them to OME-TIFF files in the output folder.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    input_files = [f for f in os.listdir(input_folder) if f.lower().endswith(('.qptiff', '.im3'))]
    
    if not input_files:
        print(f"No .qptiff or .im3 files found in {input_folder}.")
        return
    
    for input_file in input_files:
        input_path = os.path.join(input_folder, input_file)
        output_file = os.path.splitext(input_file)[0] + ".ome.tiff"
        output_path = os.path.join(output_folder, output_file)
        convert_to_ometiff(input_path, output_path)

def unmix_channels(file_path, output_path, unmix_coeff=0.3, unmixing_matrix_data=None):
    """
    Unmixes channels in an OME-TIFF file and saves the result as a new OME-TIFF file.
    """
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
        
        # Prepare the unmixed data array
        unmixed_data = np.zeros((channel_count, size_y, size_x), dtype=np.uint8)
        
        # Read all channel data into a single array
        all_channel_data = np.zeros((channel_count, size_y, size_x), dtype=np.uint8)
        for i in range(channel_count):
            channel_data = reader.openBytes(i)
            all_channel_data[i] = np.frombuffer(channel_data, dtype=np.uint8).reshape((size_y, size_x))
        
        # Apply unmixing matrix if provided
        if unmixing_matrix_data is not None:
            unmixing_matrix = unmixing_matrix_data['unmixing_matrix']
            flat_channel_data = all_channel_data.reshape(channel_count, -1)
            unmixed_flat_data = np.dot(unmixing_matrix, flat_channel_data)
            unmixed_data[:unmixing_matrix.shape[0]] = unmixed_flat_data.reshape(unmixing_matrix.shape[0], size_y, size_x)
        
        # Save the unmixed data to a new OME-TIFF file
        tifffile.imwrite(output_path, unmixed_data, photometric='minisblack', metadata={'axes': 'CYX'})
        print(f"Unmixed data saved to {output_path}")
    finally:
        reader.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert files to OME-TIFF and optionally unmix channels.")
    parser.add_argument("--input", help="Path to the input file (.qptiff, .im3, or .ome.tiff) or folder containing such files")
    parser.add_argument("--output", help="Path to the output OME-TIFF file or folder")
    parser.add_argument("--unmixing_matrix", help="Path to the unmixing matrix .npy file", default=None)
    args = parser.parse_args()

    # Check if input is a folder or a single file
    if os.path.isdir(args.input):
        if not args.output:
            print("Please specify an output folder when processing a folder.")
            exit(1)
        process_folder(args.input, args.output)
    else:
        # Single file processing
        input_ext = os.path.splitext(args.input)[1].lower()
        if input_ext in [".qptiff", ".im3"]:
            convert_to_ometiff(args.input, args.output)
        elif input_ext == ".ome.tiff":
            print(f"Input file {args.input} is already in OME-TIFF format.")
        else:
            print(f"Unsupported file format: {input_ext}")
            exit(1)

        # Load unmixing matrix if provided
        unmixing_matrix_data = None
        if args.unmixing_matrix:
            unmixing_matrix_data = np.load(args.unmixing_matrix, allow_pickle=True).item()

        # Perform unmixing if an unmixing matrix is provided
        if unmixing_matrix_data:
            unmix_channels(args.output, args.output, unmixing_matrix_data=unmixing_matrix_data)

