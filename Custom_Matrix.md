# Generating a Custom Unmixing Matrix

This guide provides instructions on how to generate a custom unmixing matrix `.npy` file using your own single stain QPTIFF files and the `gen_unmixing_matrix.py` script.

## Prerequisites

1. **Python**: Ensure you have Python 3.8 or later installed. You can download it from [python.org](https://www.python.org/downloads/).

2. **Java**: Ensure you have Java 8 or later installed. You can download it from [java.com](https://www.java.com/en/download/).

3. **Maven**: Ensure you have Maven installed. You can download it from [maven.apache.org](https://maven.apache.org/download.cgi).

4. **Conda**: It is recommended to use Conda for managing the Python environment. You can download it from [conda.io](https://docs.conda.io/en/latest/miniconda.html).


## Preparing Your Data

1. **Collect Single Stain QPTIFF Files**:
    - Place all your single stain QPTIFF files in a folder. Each file should contain images of a single stain.

2. **Ensure Channel Naming**:
    - Ensure that the channels in your QPTIFF files are correctly named, especially the 'Sample AF' and 'DAPI' channels.

## Generating the Unmixing Matrix

1. **Run the Script**:
    - Use the gen_unmixing_matrix.py script to generate the unmixing matrix. Replace `path/to/single_stain_folder` with the path to your folder containing the single stain QPTIFF files, and `path/to/output_unmixing_matrix.npy` with the desired output file path.

    ```bash
    python gen_unmixing_matrix.py path/to/single_stain_folder path/to/output_unmixing_matrix.npy
    ```

2. **Output**:
    - The script will read the single stain QPTIFF files, remove the 'Sample AF' and 'DAPI' channels from the other channels, and compute the unmixing matrix.
    - The unmixing matrix will be saved to the specified output file in `.npy` format. 

    You can then use this with the `unmix_convert.py` and `unmix_convert_with_pyramids.py` script to unmix the channels in your multi-stain QPTIFF files.

## Example Usage

```bash
python gen_unmixing_matrix.py /Users/as-hunt/Opal_unmixing/single_stain /Users/as-hunt/Opal_unmixing/output_unmixing_matrix.npy
```
