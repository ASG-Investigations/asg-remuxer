#!/usr/bin/env python3

import os
import subprocess
import sys
import gi
import threading
from queue import Queue, Empty

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

class RemuxerApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="ASG Remuxer")

        self.set_default_size(600, 400)
        self.set_border_width(10)

        self.processing = False
        self.stop_processing = False
        self.mount_points_info = {}
        self.mount_point_threads = []
        self.message_index = 0
        self.message_timer_id = None
        self.progress_pulse_timer = None  # Timer for progress bar pulsing

        # Funny messages to display
        self.funny_messages = [
            "Processing... Time to grab a coffee!",
            "Good things come to those who wait...",
            "Patience is a virtue, remuxing is an art.",
            "Hold tight, magic is happening!",
            "Transforming bits and bytes, please stand by.",
            "Almost there... maybe.",
            "Your files are in good hands.",
            "This might take a minute... or two.",
            "Remuxing in progress, do not disturb.",
            "Please wait, we're making pixels dance.",
            "Converting files and saving the world.",
            "Still here? We're working on it!",
            "Sit back, relax, and enjoy the show.",
            "Processing... it's not you, it's me.",
            "Just a little longer, promise!",
            "Working hard or hardly working? Definitely working hard.",
            "The cake is a lie, but the remuxing is real.",
            "We apologize for the inconvenience. The remuxing will be done shortly.",
            "Loading... please insert coin.",
            "If you can read this, you're too close to the screen."
        ]

        # Main vertical box
        vbox = Gtk.VBox(spacing=10)
        self.add(vbox)

        # Start and Emergency Stop buttons
        button_box = Gtk.HBox(spacing=10)
        vbox.pack_start(button_box, False, False, 0)

        self.start_button = Gtk.Button(label="Start")
        self.start_button.connect("clicked", self.on_start_clicked)
        button_box.pack_start(self.start_button, True, True, 0)

        self.stop_button = Gtk.Button(label="Emergency Stop")
        # Set the button color to red using CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        #emergency_button {
            background: red;
            color: white;
        }
        """)
        self.stop_button.set_name("emergency_button")
        style_context = self.stop_button.get_style_context()
        style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.stop_button.set_sensitive(False)
        button_box.pack_start(self.stop_button, True, True, 0)

        # Status label
        self.status_label = Gtk.Label(label="Press Start to begin")
        vbox.pack_start(self.status_label, False, False, 0)

        # Progress bar in activity mode
        self.progress_bar = Gtk.ProgressBar()
        vbox.pack_start(self.progress_bar, False, False, 0)

        # TreeView for mount points and file counts
        self.liststore = Gtk.ListStore(str, int, int)  # Mount Point, Raw Files, Processed Files
        self.treeview = Gtk.TreeView(model=self.liststore)

        for i, column_title in enumerate(["Mount Point", "Raw Files", "Processed Files"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            self.treeview.append_column(column)

        treeview_scroll = Gtk.ScrolledWindow()
        treeview_scroll.add(self.treeview)
        vbox.pack_start(treeview_scroll, True, True, 0)

        self.show_all()

    def on_start_clicked(self, widget):
        if self.processing:
            return

        self.processing = True
        self.stop_processing = False
        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.status_label.set_text("Starting remuxing process...")
        self.liststore.clear()
        self.mount_points_info.clear()
        self.mount_point_threads = []

        # Start the processing in a separate thread
        threading.Thread(target=self.start_processing).start()

        # Start the message rotation after 30 seconds
        GLib.timeout_add_seconds(30, self.start_message_rotation)

        # Start the progress bar pulsing
        self.progress_bar.set_pulse_step(0.1)
        self.progress_pulse_timer = GLib.timeout_add(100, self.pulse_progress_bar)

    def on_stop_clicked(self, widget):
        if not self.processing:
            return

        self.stop_processing = True
        self.status_label.set_text("Emergency stop initiated. Please wait...")
        self.stop_button.set_sensitive(False)

        # Wait for all mount point threads to finish
        threading.Thread(target=self.emergency_stop).start()

    def emergency_stop(self):
        # Wait for all mount point threads to finish
        for thread in self.mount_point_threads:
            thread.join()

        # Stop the message rotation if it's running
        if self.message_timer_id:
            GLib.source_remove(self.message_timer_id)
            self.message_timer_id = None

        # Stop the progress bar pulsing
        if self.progress_pulse_timer:
            GLib.source_remove(self.progress_pulse_timer)
            self.progress_pulse_timer = None
            GLib.idle_add(self.progress_bar.set_fraction, 0)

        self.processing = False
        GLib.idle_add(self.start_button.set_sensitive, True)
        GLib.idle_add(self.update_status, "Emergency stop completed.")

    def start_processing(self):
        # Check if FFmpeg is installed
        if not self.check_ffmpeg():
            self.update_status("FFmpeg command not found. Please install FFmpeg.")
            self.processing = False
            GLib.idle_add(self.start_button.set_sensitive, True)
            return

        # Get the current username
        username = os.getlogin()
        base_dir = f"/media/{username}/SPYCAM"

        mount_points = []

        # Loop through each potential mount point
        for i in range(10):
            mount_point = base_dir if i == 0 else f"{base_dir}{i}"

            if os.path.isdir(mount_point):
                mount_points.append(mount_point)

        if not mount_points:
            self.update_status("No mount points found.")
            self.processing = False
            GLib.idle_add(self.start_button.set_sensitive, True)
            return

        # Initialize mount points info and TreeView
        for mount_point in mount_points:
            self.mount_points_info[mount_point] = {
                'raw_files': 0,
                'processed_files': 0,
                'iter': self.liststore.append([mount_point, 0, 0])
            }

        # Start updating counters every 5 seconds
        GLib.timeout_add_seconds(5, self.update_counters)

        # Start processing each mount point in its own thread
        for mount_point in mount_points:
            thread = threading.Thread(target=self.process_mount_point, args=(mount_point,))
            thread.start()
            self.mount_point_threads.append(thread)

        # Wait for all threads to finish
        for thread in self.mount_point_threads:
            thread.join()

        # Stop the message rotation if it's running
        if self.message_timer_id:
            GLib.source_remove(self.message_timer_id)
            self.message_timer_id = None

        # Stop the progress bar pulsing
        if self.progress_pulse_timer:
            GLib.source_remove(self.progress_pulse_timer)
            self.progress_pulse_timer = None
            GLib.idle_add(self.progress_bar.set_fraction, 0)

        self.processing = False
        GLib.idle_add(self.start_button.set_sensitive, True)
        GLib.idle_add(self.stop_button.set_sensitive, False)

        GLib.idle_add(self.update_status, "All done!!")

    def process_mount_point(self, mount_point):
        output_dir = os.path.join(mount_point, 'mp4')
        os.makedirs(output_dir, exist_ok=True)

        # Create a queue of h264 files
        file_queue = Queue()

        # Get list of .h264 files
        for root, dirs, files in os.walk(mount_point):
            for file in files:
                if file.endswith('.h264'):
                    file_queue.put(os.path.join(root, file))

        # Create a thread pool with 4 worker threads for this mount point
        num_workers = 4
        workers = []
        for _ in range(num_workers):
            t = threading.Thread(target=self.worker_thread_mount_point, args=(file_queue, output_dir, mount_point))
            t.start()
            workers.append(t)

        # Wait for all threads to finish
        for t in workers:
            t.join()

        # After processing, update the counts one last time
        GLib.idle_add(self.update_counts)

    def worker_thread_mount_point(self, file_queue, output_dir, mount_point):
        while not self.stop_processing:
            try:
                h264_file = file_queue.get_nowait()
            except Empty:
                break  # No more files
            self.remux_and_delete(h264_file, output_dir)
            self.update_mount_point_counts(mount_point)
            file_queue.task_done()

    def update_counters(self):
        if not self.processing:
            return False  # Stop the timer

        self.update_counts()
        return True  # Continue calling every 5 seconds

    def update_counts(self):
        for mount_point in self.mount_points_info.keys():
            self.update_mount_point_counts(mount_point)

    def update_mount_point_counts(self, mount_point):
        raw_files = 0
        processed_files = 0

        output_dir = os.path.join(mount_point, 'mp4')

        for root, dirs, files in os.walk(mount_point):
            for file in files:
                if file.endswith('.h264'):
                    raw_files += 1

        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file.endswith('.mp4'):
                    processed_files += 1

        self.mount_points_info[mount_point]['raw_files'] = raw_files
        self.mount_points_info[mount_point]['processed_files'] = processed_files

        iter = self.mount_points_info[mount_point]['iter']
        GLib.idle_add(self.liststore.set_value, iter, 1, raw_files)
        GLib.idle_add(self.liststore.set_value, iter, 2, processed_files)

    def pulse_progress_bar(self):
        if not self.processing:
            return False  # Stop the timer
        GLib.idle_add(self.progress_bar.pulse)
        return True  # Continue pulsing

    def start_message_rotation(self):
        if not self.processing:
            return False  # Stop the timer if processing is not ongoing

        self.message_index = 0
        self.show_next_message()
        return False  # Stop the initial timer

    def show_next_message(self):
        if not self.processing:
            return False  # Stop the timer

        message = self.funny_messages[self.message_index]
        GLib.idle_add(self.update_status, message)

        self.message_index = (self.message_index + 1) % len(self.funny_messages)

        # Schedule the next message in 60 seconds
        self.message_timer_id = GLib.timeout_add_seconds(60, self.show_next_message)
        return False  # Do not continue the timer automatically

    def update_status(self, message):
        GLib.idle_add(self.status_label.set_text, message)

    def check_ffmpeg(self):
        """Check if FFmpeg is installed."""
        try:
            result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            return False
        return False

    def remux_and_delete(self, h264_file, output_dir):
        """Remux a .h264 file to .mp4 and delete the original if successful."""
        if self.stop_processing:
            return

        base_name = os.path.splitext(os.path.basename(h264_file))[0]
        output_file = os.path.join(output_dir, base_name + '.mp4')

        # Remux to MP4 using FFmpeg
        cmd = ['ffmpeg', '-r', '30', '-i', h264_file, '-vcodec', 'copy', output_file]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = proc.communicate()

            if self.stop_processing:
                proc.terminate()
                if os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                        print(f"Deleted incomplete file: {output_file}")
                    except Exception as e:
                        print(f"Error deleting file {output_file}: {e}")
                return

            if proc.returncode == 0:
                os.remove(h264_file)
                print(f"Removed original file: {h264_file}")
            else:
                print(f"Error remuxing file: {h264_file}\n{stderr}")
        except Exception as e:
            print(f"Exception while remuxing file: {h264_file}\n{e}")

if __name__ == '__main__':
    app = RemuxerApp()
    app.connect("destroy", Gtk.main_quit)
    Gtk.main()

