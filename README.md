# ASG Remuxer

A GUI application to remux `.h264` files to `.mp4`, processing multiple files concurrently.

## Features

- Concurrent processing of multiple files
- Progress indication with a pulsing progress bar
- Real-time file counts for raw and processed files
- Emergency Stop functionality
- Funny status messages during processing
- Note: SD card must be name SPYCAM for script to function correctly

## Installation

See the [Releases](https://github.com/ASG-Investigations/asg-remuxer/releases) page to download the `.deb` package.

### Install Dependencies

Ensure the following packages are installed:

```bash
sudo apt-get install -y python3 python3-gi gir1.2-gtk-3.0 ffmpeg

