#!/usr/bin/env python
"""
Line Scan TIFF to OME-TIFF Generator

Specialized script for handling line scan TIFF files from Akoya InForm software.
These are unusual tiles that are very short in height (6px) but wide.

Requirements:
- tifffile
- numpy 
- matplotlib (for visualization)
"""

import os
import sys
import time
import glob
import re
import argparse
import numpy as np
import tifffile
import logging
from tifffile import TiffWriter
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_coordinates(filename):
    """Extract [x,y] coordinates from filename."""
    match = re.search(r'\[(\d+),(\d+)\]', filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

def find_tiff_files(folder_path, pattern=None):
    """Find all TIFF files in the given folder, optionally matching a pattern."""
    folder_path = Path(folder_path)
    all_files = []
    
    # Find all TIFF files
    for ext in ['*.tif', '*.tiff', '*.TIF', '*.TIFF']:
        all_files.extend(folder_path.glob(ext))
    
    # Filter by pattern if specified
    if pattern:
        pattern_regex = re.compile(pattern.replace('*', '.*'))
        all_files = [f for f in all_files if pattern_regex.search(f.name)]
    
    return all_files

def get_image_dimensions(file_path):
    """Get dimensions of an image using tifffile."""
    with tifffile.TiffFile(file_path) as tif:
        page = tif.pages[0]
        width = page.imagewidth
        height = page.imagelength
        
        # Try to determine number of channels
        if page.samplesperpixel > 1:
            channels = page.samplesperpixel
        else:
            # Check if we have extra dimensions in the data
            img = tif.asarray()
            if len(img.shape) > 2:
                channels = img.shape[2]
            else:
                channels = 1
    
    return width, height, channels

def analyze_files(files):
    """Analyze all files to determine canvas size and data properties."""
    coordinates = []
    dimensions = []
    max_x = 0
    max_y = 0
    max_width = 0
    max_height = 0
    
    for file in files:
        x, y = extract_coordinates(file.name)
        if x is None or y is None:
            logger.warning(f"Could not extract coordinates from {file.name}")
            continue
            
        try:
            width, height, channels = get_image_dimensions(file)
            logger.info(f"File {file.name}: pos=({x},{y}), size={width}x{height}, channels={channels}")
            
            max_x = max(max_x, x + width)
            max_y = max(max_y, y + height)
            max_width = max(max_width, width)
            max_height = max(max_height, height)
            
            coordinates.append((x, y))
            dimensions.append((width, height, channels))
        except Exception as e:
            logger.error(f"Error analyzing {file}: {str(e)}")
    
    return coordinates, dimensions, max_x, max_y, max_width, max_height

def read_tiff(file_path):
    """Read TIFF file, handling specials cases for line scans."""
    try:
        with tifffile.TiffFile(file_path) as tif:
            img = tif.asarray()
            
            # Handle special case for Akoya component data
            if 'component_data' in str(file_path):
                # Check if this is a tall, thin image that could be reshaped
                if len(img.shape) == 2 and img.shape[0] % 6 == 0:
                    width = img.shape[1]
                    height = 6
                    channels = img.shape[0] // height
                    
                    # Reshape to proper format (H, W, C)
                    reshaped = np.zeros((height, width, channels), dtype=img.dtype)
                    for c in range(channels):
                        reshaped[:, :, c] = img[c*height:(c+1)*height, :]
                    
                    logger.info(f"Reshaped image from {img.shape} to {reshaped.shape}")
                    return reshaped
                
                # If we have too many channels, limit to 6 (common for Akoya)
                if len(img.shape) == 3 and img.shape[2] > 6:
                    logger.info(f"Limiting channels from {img.shape[2]} to 6")
                    return img[:, :, :6]
            
            return img
            
    except Exception as e:
        logger.error(f"Error reading {file_path}: {str(e)}")
        return None

def create_canvas(max_x, max_y, num_channels, dtype=np.uint16):
    """Create an empty canvas with buffer space."""
    # Add a small buffer
    max_x += 20
    max_y += 20
    
    logger.info(f"Creating canvas of size {max_y}x{max_x} with {num_channels} channels")
    return np.zeros((max_y, max_x, num_channels), dtype=dtype)

def place_image_on_canvas(canvas, img, x, y):
    """Place image on canvas at specified coordinates, handling edge cases."""
    if img is None:
        return canvas
    
    # Get image dimensions
    if len(img.shape) == 2:
        h, w = img.shape
        # Convert to 3D for single channel images
        img_3d = np.zeros((h, w, 1), dtype=img.dtype)
        img_3d[:, :, 0] = img
        img = img_3d
    else:
        h, w, c = img.shape
    
    # Calculate target region
    end_y = min(y + h, canvas.shape[0])
    end_x = min(x + w, canvas.shape[1])
    
    # Calculate source region
    src_h = end_y - y
    src_w = end_x - x
    
    # Skip if outside canvas
    if src_h <= 0 or src_w <= 0 or x >= canvas.shape[1] or y >= canvas.shape[0]:
        logger.warning(f"Image at ({x},{y}) size {w}x{h} falls outside canvas")
        return canvas
    
    # Copy channels one by one to avoid shape mismatch issues
    ch_to_copy = min(img.shape[2], canvas.shape[2])
    try:
        for c in range(ch_to_copy):
            canvas[y:end_y, x:end_x, c] = img[:src_h, :src_w, c]
    except Exception as e:
        logger.error(f"Error copying image: {e}")
        logger.error(f"Canvas region: {canvas[y:end_y, x:end_x].shape}, Source: {img[:src_h, :src_w].shape}")
    
    return canvas

def write_ome_tiff(output_path, img, channel_names, compression='zlib', tile_size=512):
    """Write pyramidal OME-TIFF with metadata."""
    # Generate pyramid levels
    pyramid = [img]
    current = img
    
    while current.shape[0] > 256 and current.shape[1] > 256:
        # Calculate new dimensions - handle odd sizes properly
        h, w = current.shape[0], current.shape[1]
        new_h, new_w = h // 2, w // 2
        
        # Create properly sized array for downsampled image
        if len(current.shape) == 3:
            c = current.shape[2]
            downsampled = np.zeros((new_h, new_w, c), dtype=current.dtype)
            
            # Downsample each channel individually with explicit indexing
            for i in range(c):
                # Manual downsampling with proper indexing - avoid broadcasting errors
                for y in range(new_h):
                    for x in range(new_w):
                        downsampled[y, x, i] = current[y*2, x*2, i]
        else:
            downsampled = np.zeros((new_h, new_w), dtype=current.dtype)
            # Manual downsampling with proper indexing
            for y in range(new_h):
                for x in range(new_w):
                    downsampled[y, x] = current[y*2, x*2]
        
        pyramid.append(downsampled)
        current = downsampled
    
    # Generate OME-XML metadata with enhanced channel information
    ome_xml = '<?xml version="1.0" encoding="UTF-8"?>'
    ome_xml += '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06" '
    ome_xml += 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    ome_xml += 'xsi:schemaLocation="http://www.openmicroscopy.org/Schemas/OME/2016-06 http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd">'
    
    # Add image metadata
    if len(img.shape) == 3:
        height, width, channels = img.shape
    else:
        height, width = img.shape
        channels = 1
        
    # Set appropriate colors for Akoya Opal dyes and map dye names to wavelengths
    channel_metadata = {
        'DAPI': {'color': '0000FF', 'emission': 461, 'excitation': 358, 'fluor': 'DAPI'},
        'Opal 480': {'color': '00FFFF', 'emission': 523, 'excitation': 494, 'fluor': 'Opal 480'},
        'Opal 520': {'color': '00FF00', 'emission': 565, 'excitation': 494, 'fluor': 'Opal 520'},
        'Opal 570': {'color': 'FFFF00', 'emission': 570, 'excitation': 555, 'fluor': 'Opal 570'},
        'Opal 620': {'color': 'FF0000', 'emission': 620, 'excitation': 588, 'fluor': 'Opal 620'},
        'Sample AF': {'color': 'FFFFFF', 'emission': 500, 'excitation': 488, 'fluor': 'Autofluorescence'},
        # Generic channel fallback
        'default': {'color': 'FFFFFF', 'emission': 500, 'excitation': 488, 'fluor': 'Unknown'}
    }
    
    ome_xml += f'<Image ID="Image:0" Name="Merged Image">'
    ome_xml += f'<Pixels ID="Pixels:0" DimensionOrder="XYCZT" Type="{img.dtype}" '
    ome_xml += f'SizeX="{width}" SizeY="{height}" SizeC="{channels}" SizeZ="1" SizeT="1" '
    ome_xml += f'PhysicalSizeX="1.0" PhysicalSizeY="1.0" PhysicalSizeXUnit="µm" PhysicalSizeYUnit="µm">'
    
    # Add channel metadata with more detailed information
    for i in range(channels):
        ch_name = channel_names[i] if i < len(channel_names) else f"Channel {i+1}"
        
        # Get metadata for this channel, defaulting to generic values if not found
        meta = channel_metadata.get(ch_name, channel_metadata['default'])
        
        ome_xml += f'<Channel ID="Channel:0:{i}" Name="{ch_name}" '
        ome_xml += f'SamplesPerPixel="1" Color="{meta["color"]}" '
        
        # Add fluorophore information
        if 'fluor' in meta:
            ome_xml += f'Fluor="{meta["fluor"]}" '
        if 'emission' in meta:
            ome_xml += f'EmissionWavelength="{meta["emission"]}" '
        if 'excitation' in meta:
            ome_xml += f'ExcitationWavelength="{meta["excitation"]}" '
            
        ome_xml += '/>'
    
    ome_xml += '</Pixels></Image></OME>'
    
    # Write the OME-TIFF
    with TiffWriter(output_path, bigtiff=True) as tif:
        options = {
            'compression': compression,
            'metadata': {'description': ome_xml},
            'photometric': 'minisblack',
            'tile': (tile_size, tile_size),
            'resolution': (1.0, 1.0),
            'resolutionunit': 'NONE'
        }
        
        # Write each level
        for i, level in enumerate(pyramid):
            if i > 0:
                options['subfiletype'] = 1  # FILETYPE_REDUCEDIMAGE
            tif.write(level, **options)
    
    logger.info(f"Saved OME-TIFF to {output_path} with enhanced channel metadata")

def main():
    parser = argparse.ArgumentParser(description='Convert line scan TIFF tiles to pyramidal OME-TIFF')
    parser.add_argument('--folder', required=True, help='Folder containing TIFF tiles')
    parser.add_argument('--output', required=True, help='Output OME-TIFF file')
    parser.add_argument('--pattern', help='Pattern to match filenames (e.g. "component_data")')
    parser.add_argument('--channels', type=int, default=6, help='Number of channels (default: 6)')
    parser.add_argument('--channel-names', nargs='+', 
                        default=['DAPI', 'Opal 480', 'Opal 520', 'Opal 570', 'Opal 620', 'Sample AF'],
                        help='Channel names')
    parser.add_argument('--compression', default='zlib', choices=['zlib', 'lzma', 'jpeg', 'none'],
                        help='Compression type (default: zlib)')
    args = parser.parse_args()
    
    # Find files
    logger.info(f"Searching for TIFF files in {args.folder}")
    files = find_tiff_files(args.folder, args.pattern)
    logger.info(f"Found {len(files)} TIFF files")
    
    if not files:
        logger.error("No matching files found.")
        return
    
    # Analyze files to determine overall dimensions
    logger.info("Analyzing files to determine dimensions...")
    coordinates, dimensions, max_x, max_y, max_width, max_height = analyze_files(files)
    logger.info(f"Canvas size will be {max_y}x{max_x} with {args.channels} channels")
    
    # Create empty canvas
    canvas = create_canvas(max_x, max_y, args.channels)
    
    # Process each file
    logger.info("Placing images on canvas...")
    for i, file in enumerate(files):
        x, y = extract_coordinates(file.name)
        if x is None or y is None:
            continue
            
        logger.info(f"Processing file {i+1}/{len(files)}: {file.name}")
        img = read_tiff(file)
        canvas = place_image_on_canvas(canvas, img, x, y)
    
    # Write the final OME-TIFF
    logger.info(f"Writing OME-TIFF to {args.output}...")
    write_ome_tiff(args.output, canvas, args.channel_names, compression=args.compression)
    logger.info("Done!")

if __name__ == "__main__":
    main()