# Opal Unmixing

Script for working with QPTIFF files and Opal unmixing Sample AF from the other channels.

This will generate big image files! About 2-8Gb for non pyramidal images and 10-40Gb for pyramidal images.

## Installation

### Prerequisites

Required software: Python3, Java, Maven
Recommended to use conda to manage environments.

### Installation

This was only tested on Mac OS and Linux through docker. It should work on Windows, but it has not been tested.

#### Mac OS
```bash
    brew install miniconda openjdk maven temurin
    conda create --name opal python=3.12
    conda activate opal
```

#### Linux
 ```bash
    sudo apt-get install miniconda openjdk maven
    conda create --name opal python=3.12
    conda activate opal
```

#### Windows

Install miniconda, openjdk, and maven. Then create a new environment with python 3.12.

```bash
    conda create --name opal python=3.12
    conda activate opal
 ```

### Clone the Repository
```bash
    git clone https://github.com/alex1075/Opal-unmixing.git
    cd Opal_unmixing
 ```


### Install Python Dependencies
```bash
    pip install -r requirements.txt
```

### Install Java dependencies using Maven
```bash
    mvn clean install
```

### Running the Script


To run the script for unmixing channels in a QPTIFF file ONLY, use the following command:

```bash
    python unmix_convert.py <input_file> <output_file> 

```

To run the script for unmixing channels in a QPTIFF file and generate a pyramidal image, use the following command:    

```bash
    python unmix_convert.py <input_file> <output_file> 

```