# name: main.py
# author: Lorenz Siedler
# last modified: 30.07.2021

# description: Small Description Editor with implemented Speech-to-Text algorithms.

# User interactions:

import os
import glob
import queue
import threading
import time
import tkinter.ttk as ttk
from tkinter import *
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText
from tkinter import colorchooser
from tkinter import font
import audioread
import numpy as np

# Audio player
import pygame
from mutagen.mp3 import MP3

# Audio wave view
import scipy.io
import scipy.io.wavfile
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# Speech recognition
from pydub import AudioSegment
from pydub.silence import split_on_silence
import speech_recognition as sr
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_watson import SpeechToTextV1

# from wit import Wit

matplotlib.use('TkAgg')

# IBM Watson Access
authenticator = IAMAuthenticator('<insert personal token here>')
ibm_stt_algorithm = SpeechToTextV1(
    authenticator=authenticator
)
ibm_stt_algorithm.set_service_url('<insert personal URL here>')

# Google Cloud API
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "< insert path to SERVICE_ACCOUNT_KEY.JSON>"

# Houndify API
HOUNDIFY_CLIENT_ID = "<insert Houndify Client ID here>"
HOUNDIFY_CLIENT_KEY = "<insert Houndify Client Key here>"

# create a speech recognition object
r = sr.Recognizer()

# Initialize the pygame mixer
pygame.mixer.init()

# Global Variables
audio_file_dict_mp3 = {}
audio_file_dict_wav = {}
duration = 0
paused = False

global stopped
global audio
global cur_sel
global converted_audio_length
global song_length

# Audio wave view global variable
startxlim = [0.0, 5.0]  # starting x range in data coordinates
zcount = 0.0  # zoom level counter
lastevtime = 0  # last event time(stamp)

# Audio vertical lines
pos_1 = False
pos_2 = False


# Thread class
# used from http://code.activestate.com/recipes/82965-threads-tkinter-and-asynchronous-io/download/1/
class ThreadedClient:

    def __init__(self, master):
        # Start the GUI and the asynchronous threads. We are in the main
        # (original) thread of the application, which will later be used by
        # the GUI. We spawn a new thread for the worker.

        self.master = master

        # Create the queue
        self.queue = queue.Queue()

        self.running = 1

        # Start the periodic call to check if the queue contains
        # anything
        self.periodicCall()

    def periodicCall(self):
        # Check every 66 ms if there is something new in the queue.
        # Handle all the messages currently in the queue (if any).

        doUpdate = 0
        # ~ print "self.queue.qsize", self.queue.qsize()
        while self.queue.qsize():
            try:
                msg = self.queue.get(block=False)
                print(msg)
                # There were some messages, so do update
                doUpdate = 1
            # Exception handling
            except queue.Empty:
                doUpdate = 0  # don't do updates
        if not self.running:
            # This is the brutal stop of the system. You may want to do
            # some cleanup before actually shutting it down.
            import sys
            sys.exit(1)
        # ~ print doUpdate, self.queue.qsize()
        if doUpdate:
            updateWindow()
        # 66 ms for ca. 15 fps
        self.master.after(66, self.periodicCall)

    def endApplication(self):
        self.running = 0


# function for setting the audio wave viewer at a specific x position
def gototf_Return(self):
    # get the global subplot object
    global ax_1

    try:
        # get the desired value of the user
        gotoval = float(go_to_x_position.get())
    # Exception handling
    except Exception as e:
        # print the exception and return the function
        print("Error, not going anywhere: ", sys.exc_info()[1], sys.exc_info()[0], e)
        return

    # get the current limitations of the x axis of the audio wave viewer
    xmin_datac, xmax_datac = ax_1.get_xlim()
    # calculate the current range of the audio wave viewer in x direction
    xrange = xmax_datac - xmin_datac
    # center current zoom level around requested x value
    ax_1.set_xlim(gotoval - 0.5 * xrange, gotoval + 0.5 * xrange)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# function for setting the desired zoom of the audio wave viewer at a specific value
def zoomtf_Return(self):
    # get the global subplot object
    global ax_1
    # get the current zoom level
    global zcount

    try:
        # DEBUG Print
        print("zoomtf_Return")
        # get the desired zoom level of the user
        zoomval = int(float(go_to_x_zoom.get()))
    # Exception handling
    except Exception as e:
        # print the exception and return the function
        print("Error, not going anywhere: ", sys.exc_info()[1], sys.exc_info()[0], e)
        return

    # store the deired zoom level into the global variable
    zcount = zoomval

    # recalculate zoom in respect to midpoint
    dfact = 1.0 - (1.0 / (1.1 ** zcount))
    # get the current limitations of the x axis of the audio wave viewer
    xmin_datac, xmax_datac = ax_1.get_xlim()
    # calculate the current range of the audio wave viewer in x direction
    oxrange = xmax_datac - xmin_datac

    # calculate the right and left boundaries for the desired zoom
    # calculate the center x-position
    mous_xloc_datac = xmin_datac + 0.5 * oxrange
    # calculate the distance between the center and the right limit
    odxright = xmax_datac - mous_xloc_datac
    # calculate the distance between the center and the left limit
    odxleft = mous_xloc_datac - xmin_datac
    # calculate the half distance of constant starting range [0.00;5.00]
    srange_half = (startxlim[1] - startxlim[0]) / 2.0
    # recalculate the new range between the left and the right limit
    newxrange = (startxlim[1] - srange_half * dfact) - (startxlim[0] + srange_half * dfact)
    # calculate the quotient of the new range compared to the current range
    nrxfact = newxrange / oxrange

    # set the new x limitation boundaries for the desired zoom with the x-position as center
    ax_1.set_xlim(mous_xloc_datac - odxleft * nrxfact, mous_xloc_datac + odxright * nrxfact)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# function to set the first vertical line the the audio wave viewer
def position_1_vertical_line(self):
    # get the global variables and the subplot
    global position_1, pos_1, ax_1

    try:
        # DEBUG print
        print("position_1_vertical_line")
        # get the desired position of the first vertical line from the user
        x = float(get_to_position_1.get())
        # DEBUG print - x position
        print("x: ", x)
    # Exception handling
    except Exception as e:
        # print the exception and return the function
        print("Error, not going anywhere: ", sys.exc_info()[1], sys.exc_info()[0], e)
        return

    # if there is no current vertical position 1 line drawn in the audio wave viewer, draw one
    if not pos_1:
        # add the vertical line to the audio wave viewer
        position_1 = ax_1.axvline(x=x, lw=2, c="orange", label="Position 2")
        # set the global variable to true to mark that the vertical line was added to the subplot
        pos_1 = True
    # if there is already a vertica position 1 line drawn in the audio wave viewer, change only the position
    else:
        # DEBUG print
        print("Position_1 X Data: ", position_1.get_xdata(self))
        # change the x-position of the vertical position 1 line to the desired position
        position_1.set_xdata([x, x])

    # DEBUG print - new position
    print("Position 1: ", position_1)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# function to set the second vertical line the the audio wave viewer
def position_2_vertical_line(self):
    # get the global variables and the subplot
    global position_2, pos_2, ax_1

    try:
        # DEBUG print
        print("position_2_vertical_line")
        # get the desired position of the first vertical line from the user
        x = float(get_to_position_2.get())
        # DEBUG print - x position
        print("x: ", x)
    # Exception handling
    except Exception as e:
        # print the exception and return the function
        print("Error, not going anywhere: ", sys.exc_info()[1], sys.exc_info()[0], e)
        return

    # if there is no current vertical position 2 line drawn in the audio wave viewer, draw one
    if not pos_2:
        # add the vertical line to the audio wave viewer
        position_2 = ax_1.axvline(x=x, lw=2, c="orange", label="Position 2")
        # set the global variable to true to mark that the vertical line was added to the subplot
        pos_2 = True
    else:
        # DEBUG print
        print("Position_2 X Data: ", position_2.get_xdata(self))
        # change the x-position of the vertical position 1 line to the desired position
        position_2.set_xdata([x, x])

    # DEBUG print - new position
    print("Position 2: ", position_2)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# function to update the audio wave viewer - will be called by the update-thread
def updateWindow():
    # get the global variables and the subplot
    global ax_1, position_1, pos_1, position_2, pos_2

    try:
        # try to redraw the audio wave viewer
        canvas.draw()
    except Exception as e:
        # print the exception
        print("canvas 'crashed', not redrawing.. ")
        print("Exception: ", e)

    # Calls all pending idle tasks, without processing any other events.
    # This can be used to carry out geometry management and redraw widgets if necessary, without calling any callbacks.
    # whole application
    root.update_idletasks()
    # audio wave viewer
    canvas.get_tk_widget().update_idletasks()
    # push current to keep the  zoom history
    toolbar.push_current()

    # get the current limitations of the x axis of the audio wave viewer
    xmin_datac, xmax_datac = ax_1.get_xlim()
    # calculate the current range of the audio wave viewer in x direction
    xrange = xmax_datac - xmin_datac
    # clear the x-position entry field
    go_to_x_position.delete(0, END)
    # insert the current center x-position into the x-position entry field
    go_to_x_position.insert(0, float("{:.2f}".format(xmin_datac + 0.5 * xrange)))
    # clear the zoom entry field
    go_to_x_zoom.delete(0, END)
    # insert the current zoom value into the zoom entry field
    go_to_x_zoom.insert(0, float("{:.2f}".format(zcount)))
    # clear the position_1 entry field
    get_to_position_1.delete(0, END)
    # if there is currently no drawn vertical position_1 line, insert a 0.00 into the position_1 entry field
    if not pos_1:
        get_to_position_1.insert(0, float("{:.2f}".format(0)))
    # if there is currently a drawn vertical position_1 line, insert the current x-position of the vertical line
    # into the position_1 entry field
    else:
        get_to_position_1.insert(0, float("{:.2f}".format(position_1.get_xdata()[0])))
    # clear the position_2 entry field
    get_to_position_2.delete(0, END)
    # if there is currently no drawn vertical position_2 line, insert a 0.00 into the position_2 entry field
    if not pos_2:
        get_to_position_2.insert(0, float("{:.2f}".format(0)))
    # if there is currently a drawn vertical position_2 line, insert the current x-position of the vertical line
    # into the position_2 entry field
    else:
        get_to_position_2.insert(0, float("{:.2f}".format(position_2.get_xdata()[0])))


# function that splits the audio file into chunks and applies speech recognition algorithms on each of these chunks
def get_large_audio_transcription(path):
    # get the global variables
    global stt_algorithm, stt_config, position_1, position_2, pos_1, pos_2, script_dir, language

    # declaration of an local variables
    sound = ''
    x_1 = 0.0
    setting = 0

    # if file is an wav file
    if path.split(".")[-1] == "wav":
        # open the audio file using pydub
        sound = AudioSegment.from_wav(path)
        # DEBUG print
        print(sound)
    #  if file is an mp3 file
    elif path.split(".")[-1] == "mp3":
        # open the audio file using pydub
        sound = AudioSegment.from_mp3(path)
        # DEBUG print
        print(sound)
    # if it is neither a wav file nor a mp3 file
    else:
        # Error handling
        print("Audio file is neither a wav file nor a mp3 file.. - only wav and mp3 files")
        # return the function
        return

    # check which configuration was chosen - whole audio file or only a audio snipped marked with position 1 and 2
    # whole audio file
    if int(stt_config.get()) == 0:
        # if the whole audio file configuration was chosen, set the setting variable to 0
        setting = 0
        # pass for further processing
        pass
    # audio snippet
    elif int(stt_config.get()) == 1:
        # if the audio snippet configuration was chosen, set the setting variable to 1
        setting = 1
        # check if position 1 and 2 are set
        if pos_1 and pos_2:
            # get the x-value of the vertical position 1 and 2 lines
            x_1 = float(get_to_position_1.get())
            x_2 = float(get_to_position_2.get())

            # multiply both positions with 1000 to convert the value from seconds to milliseconds
            t1 = x_1 * 1000
            t2 = x_2 * 1000

            # check if position 1 is left from position 2
            if t1 < t2:
                # extract the specific audio snippet
                sound = sound[t1:t2]
            # check if position 2 is left from position 1
            elif t2 < t1:
                # extract the specific audio snippet
                sound = sound[t2:t1]
            # if position 1 is at the same position as position 2
            else:
                # print error message
                print("Error: Position markers are not allowed to be on the same position for STT algorithm.")
                # return the function
                return
        # if not both positions are set before performing the stt algorithm on the audio snippet
        else:
            # print error message
            print("Not both positions are set")
            # return the function
            return

    # check which language was chosen
    language_selected = int(language.get())

    # check if the audio file could be opened
    if sound:  # if sound != '':
        # split the audio sound where silence is 500 miliseconds or more and and store them in chunks
        chunks = split_on_silence(sound,
                                  # experiment with this value for your target audio file
                                  min_silence_len=500,
                                  # adjust this per requirement
                                  silence_thresh=sound.dBFS - 14,
                                  # keep the silence for 1 second, adjustable as well
                                  # keep_silence=500,
                                  # set keep_silence to True to keep the silence and the original audio length
                                  keep_silence=True,
                                  )

        # declare a local variable with the folder name, where the chunks will be stored
        folder_name = "audio-chunks"

        # if there is no directory with this name in the main directory, a new directory will be created
        if not os.path.isdir(folder_name):
            os.mkdir(folder_name)
        # if there is already a directory with this name
        else:
            # DEBUG print
            print(script_dir)
            # create the absolute path for the audio-chunks folder
            script_dir_rm = script_dir + "/" + folder_name + "/*"
            # DEBUG print
            print(script_dir_rm)
            # get all files, which are located in the audio-chunks folder
            files = glob.glob(script_dir_rm)
            # if there are files in the directory
            if files:
                # remove all files, which are located within the audio-chunks folder
                for f in files:
                    os.remove(f)
            # if there are no files in the directory
            else:
                # pass for further processing
                pass

        # declare a local variables
        whole_text = ""
        current_end_position = 0

        if setting == 0:
            # if the complete audio file configuration was choosen, set the current_start_position variable to zero
            current_start_position = 0
        else:
            # if the audio snippet configuration was choosen, get the time of the first vertical line
            # and store it into the current_start_position variable
            current_start_position = x_1

        # divide the current_start_position time into seconds and microseconds
        s, ms = divmod(current_start_position * 1000, 1000)
        # convert the start_position time into a '00:00:00.000' format
        start_position = '{}.{:0>3d}'.format(time.strftime('%H:%M:%S', time.gmtime(s)), int(ms))

        # iter over all chunks
        for i, audio_chunk in enumerate(chunks, start=1):
            # create an relative path for saving the audio chunk
            chunk_filename = os.path.join(folder_name, f"chunk{i}.wav")
            # export audio chunk and save it in the audio-chunks directory
            audio_chunk.export(chunk_filename, format="wav")

            # open the chunk file
            with audioread.audio_open(chunk_filename) as f:
                # get the chunk length in seconds
                chunk_length = f.duration

            if i == 1:
                # if it is the first iteration of the for-loop, calculate the sum of the current position
                # and the chunk length
                current_end_position = current_start_position + chunk_length
            else:
                # if is not the first iteration, calculate the sum of the current_end_position and the chunk length
                current_end_position += chunk_length

            # divide the end_position time into seconds and microseconds
            s, ms = divmod(current_end_position * 1000, 1000)
            # convert the end_position time into a '00:00:00.000' format
            end_position = '{}.{:0>3d}'.format(time.strftime('%H:%M:%S', time.gmtime(s)), int(ms))

            # recognize the chunk and apply the speech-to-text algorithm
            with sr.AudioFile(chunk_filename) as source:
                # extract audio data from the file
                audio_listened = r.record(source)

                # try converting it to text
                try:
                    # check if the configuration of the stt-algorithm are set to 0
                    if int(stt_algorithm.get()) == 0:  # Google Speech Recognition - Free (unlimited)
                        # check which language was chosen
                        if language_selected == 0:
                            # transcription in english
                            text = r.recognize_google(audio_listened, language="en-US")  # de-DE, en-US
                        else:
                            # transcription in german
                            text = r.recognize_google(audio_listened, language="de-DE")  # de-DE, en-US

                    # check if the configuration of the stt-algorithm are set to 1
                    elif int(stt_algorithm.get()) == 1:  # IBM Speech To Text - (limited to 500 minutes/month)
                        # check which language was chosen
                        if language_selected == 0:
                            # transcription in english
                            text = ibm_stt_algorithm.recognize(audio=audio_listened.get_wav_data(),
                                                               content_type='audio/wav',
                                                               model='en-US_BroadbandModel').get_result()
                        else:
                            # transcription in german
                            text = ibm_stt_algorithm.recognize(audio=audio_listened.get_wav_data(),
                                                               content_type='audio/wav',
                                                               model='de-DE_BroadbandModel').get_result()
                        # DEBUG print
                        print("Pre_Processed: ", text)
                        # try to extract the transcribed text from the json structure
                        try:
                            # if the result branch is empty, there is no transcribed text
                            if len(text["results"]) == 0:
                                text = ""
                            # else there is transcribed text
                            else:
                                # extract the transcribted text from the json structure
                                text = text["results"][0]["alternatives"][0]["transcript"][:-1]
                                # DEBUG print
                                print("Processed: ", text)
                        # Exception handling
                        except Exception as e:
                            # print the exception
                            print("Unexpected error:", sys.exc_info()[0], e)

                    # check if the configuration of the stt-algorithm are set to 2
                    elif int(stt_algorithm.get()) == 2:  # Google Cloud Speech API - (limited to 60 minutes/month)
                        # (else 0,006 $/15 seconds; free testperiod until October 21st, 2021; 252 € free test credit)
                        # 60 min free/ month - afterwards pay per minute
                        # check which language was chosen
                        if language_selected == 0:
                            # transcription in english
                            text = r.recognize_google_cloud(audio_listened, language='en-US')
                        else:
                            # transcription in german
                            text = r.recognize_google_cloud(audio_listened, language='de-DE')
                        text = text[:-1]

                    # check if the configuration of the stt-algorithm are set to 3
                    elif int(stt_algorithm.get()) == 3:  # Wit.ai - Free (unlimited)
                        # check which language was chosen
                        if language_selected == 0:
                            # transcription in english
                            text = r.recognize_wit(audio_listened, key="<insert Wit key here>")
                        else:
                            # transcription in german
                            text = r.recognize_wit(audio_listened, key="<insert Wit key here>")

                    # check if the configuration of the stt-algorithm are set to 4
                    elif int(stt_algorithm.get()) == 4:  # CMUSphinx - Free (unlimited)
                        # Only US English, German, International French, Mandarin Chinese, Italian
                        if language_selected == 0:
                            # transcription in english
                            text = r.recognize_sphinx(audio_listened)
                        else:
                            # transcription in german
                            text = r.recognize_sphinx(audio_listened, language = 'de-DE')


                    # check if the configuration of the stt-algorithm are set to 5
                    elif int(stt_algorithm.get()) == 5:  # Houndify API - Free (limited to 100 Credits/day)
                        # Currently only English - other languages are already requested
                        text = r.recognize_houndify(audio_listened, client_id=HOUNDIFY_CLIENT_ID,
                                                    client_key=HOUNDIFY_CLIENT_KEY)

                    else:
                        print("No STT-algorithm selected - cannot be happen! :-)")
                        pass

                # Exception handling
                except sr.UnknownValueError as e:
                    # print Exception
                    print("Error:", str(e))

                else:
                    # if the text variable keeps empty, skip it
                    if not text:  # if text == "":
                        pass
                    # else further process them
                    else:
                        # if the text string already contain a full stop at the end, just capitalize the first word
                        # add the start and stop position at the beginning
                        if text[-1] == ".":
                            #text = f"{start_position} - {end_position} : {text.capitalize()}\n\n"
                            text = f"{text.capitalize()}\n"
                        # else capitalize the first word and add a full stop at the end of the string
                        # add the start and stop position at the beginning
                        else:
                            #text = f"{start_position} - {end_position} : {text.capitalize()}.\n\n"
                            text = f"{text.capitalize()}.\n"

                    # DEBUG print
                    print(chunk_filename, ": ", text)
                    # add the content of the text variable to the whole_text variable, which will be insert into the
                    # scrolledText field
                    whole_text += text

                # change the previous end_position to the next start_position
                start_position = end_position

        # after all chunks are processed insert the content of the whole_text variable to the scrolledText field
        textBox.insert(INSERT, whole_text, 'translated_text')
        # insert a linebreak after the insertion of the transcribed text
        textBox.insert(END, "\n")
    else:
        print("File Handling Error")
        # textBox.insert(INSERT, "File Handling Error", 'translated_text')
        # textBox.insert(END, "\n")


# function to get the path of the selected audio file and start a thread to process the STT-algorithm on this audio file
def STT_function():
    # get the active, user selected audio file from the songbox
    audio_selected = songbox.get(ACTIVE)
    # get the absolute path from the active, user selected audio file
    audio_stt = audio_file_dict_mp3[audio_selected]

    # DEBUG print
    print(audio_stt)

    # Creates a thread for each STT-algorithm (thread terminates at the end of the function automatically)
    # Arguments: Add an extra ',' or use brackets to make a list
    STT_Thread = threading.Thread(target=get_large_audio_transcription, args=(audio_stt,))

    # Set the thread as a deamon.
    # Daemons are only useful when the main program is running,
    # and it's okay to kill them off once the other non-daemon threads have exited.
    # To designate a thread as a daemon, we call its setDaemon() method with a boolean argument.
    # The default setting for a thread is non-daemon. So, passing True turns the daemon mode on.
    STT_Thread.setDaemon(True)

    # Starts the thread's activity
    STT_Thread.start()

    # Wait until a daemon thread has completed its work.
    # STT_Thread.join()


# function which can open text files and load them into the scrolledText Entry
def onopen():
    # define the file types, which should be displayed in the file manager
    ftypes = [('Text files', '*.txt'), ('All files', '*')]
    # open file manager with above defined file types
    dlg = filedialog.Open(filetypes=ftypes)
    # try to open the file manager
    try:
        # display the file manager
        fl = dlg.show()
        # if the file is empty - pass
        if fl is None:
            pass
        # if the file is not empty
        else:
            # read the content of the file
            text = readfile(fl)
            # insert the content of the file into the scrolledText Entry
            textBox.insert(END, text)
    # exception handling
    except Exception as e:
        # print exception
        print('Error during onopen-function: ', e)


# function to read the content of the file
def readfile(filename):
    # open the file in read-mode
    f = open(filename, "r")
    # read in the the content of the file
    text = f.read()
    # return the content of the file
    return text


# function to save the content of the scrolledText field to a txt file
def save_command():
    # open and show the file manager for the saving-process - the default extension is txt
    file = filedialog.asksaveasfile(mode='w', defaultextension=".txt")
    # if file is not empty
    if file is not None:
        # get the content of the scrolledText field
        data = textBox.get('1.0', END + '-1c')
        # write the content of the scrolledText field to the file
        file.write(data)
        # close the file after writing
        file.close()


# function to open one audio file
def open_audiofile_one():
    # get the global variables
    global script_dir
    # define the file types, which should be displayed in the file manager - preferred audio types are wav and mp3
    ftypes_audio = [('Wave files', '*.wav'), ('MP3', '*.mp3'), ('All files', '*')]
    # open file manager with above defined file types and in the initial directory "./audio/"
    fl = filedialog.askopenfilename(initialdir="./audio/", title="Choose audio file", filetypes=ftypes_audio)
    # DEBUG print
    print(fl)

    if fl:  # if fl != '':
        # get the name of the audio file without the path
        fl_split = fl.split("/")[-1]
        # get the name of the audio file without the extension
        fl_split = fl_split.split(".")[0]
        # extract the extension from the file
        file_type = fl.split(".")[-1]
        # if the extension is wav
        if file_type == "wav":
            # export the audio content to a mp3 file and store them into the ./audio/temp_audio directory
            AudioSegment.from_wav(fl).export(f"{script_dir}/audio/temp_audio/{fl_split}.mp3", format="mp3")
            # DEBUG print
            print(fl.rsplit('/', 1)[0])
            # store the audiofile name and the absolute path to the mp3-audiofile into the mp3-dictionary
            audio_file_dict_mp3[fl_split] = f"{script_dir}/audio/temp_audio/{fl_split}.mp3"
            # DEBUG print
            print(audio_file_dict_mp3)
            # store the audiofile name and the absolute path to the wav-audiofile into the wav-dictionary
            audio_file_dict_wav[fl_split] = fl
            # DEBUG print
            print(audio_file_dict_wav)
        # if the extension is mp3
        elif file_type == "mp3":
            # export the audio content to a wav file and store them into the ./audio/temp_audio directory
            AudioSegment.from_mp3(fl).export(f"{script_dir}/audio/temp_audio/{fl_split}.wav", format="wav")
            # DEBUG print
            print(fl.rsplit('/', 1)[0])
            # store the audiofile name and the absolute path to the wav-audiofile into the wav-dictionary
            audio_file_dict_wav[fl_split] = f"{script_dir}/audio/temp_audio/{fl_split}.wav"
            # DEBUG print
            print(audio_file_dict_wav)
            # store the audiofile name and the absolute path to the mp3-audiofile into the mp3-dictionary
            audio_file_dict_mp3[fl_split] = fl
            # DEBUG print
            print(audio_file_dict_mp3)

        # insert the audiofile name into the songbox
        songbox.insert(END, fl_split)


# function to open multiple audio file
def open_audiofile_multiple():
    # get the global variables
    global script_dir
    # define the file types, which should be displayed in the file manager - preferred audio types are wav and mp3
    ftypes_audio = [('Wave files', '*.wav'), ('MP3', '*.mp3'), ('All files', '*')]
    # open file manager with above defined file types and in the initial directory "./audio/"
    fls = filedialog.askopenfilenames(initialdir="./audio/", title="Choose audio file", filetypes=ftypes_audio)

    for fl in fls:
        if fl:  # if fl != '':
            # get the name of the audio file without the path
            fl_split = fl.split("/")[-1]
            # get the name of the audio file without the extension
            fl_split = fl_split.split(".")[0]
            # extract the extension from the file
            file_type = fl.split(".")[-1]
            # if the extension is wav
            if file_type == "wav":
                # export the audio content to a mp3 file and store them into the ./audio/temp_audio directory
                AudioSegment.from_wav(fl).export(f"{script_dir}/audio/temp_audio/{fl_split}.mp3", format="mp3")
                # DEBUG print
                print(fl.rsplit('/', 1)[0])
                # store the audiofile name and the absolute path to the mp3-audiofile into the mp3-dictionary
                audio_file_dict_mp3[fl_split] = f"{script_dir}/audio/temp_audio/{fl_split}.mp3"
                # DEBUG print
                print(audio_file_dict_mp3)
                # store the audiofile name and the absolute path to the wav-audiofile into the wav-dictionary
                audio_file_dict_wav[fl_split] = fl
                # DEBUG print
                print(audio_file_dict_wav)
            # if the extension is mp3
            elif file_type == "mp3":
                # export the audio content to a wav file and store them into the ./audio/temp_audio directory
                AudioSegment.from_mp3(fl).export(f"{script_dir}/audio/temp_audio/{fl_split}.wav", format="wav")
                # DEBUG print
                print(fl.rsplit('/', 1)[0])
                # store the audiofile name and the absolute path to the wav-audiofile into the wav-dictionary
                audio_file_dict_wav[fl_split] = f"{script_dir}/audio/temp_audio/{fl_split}.wav"
                # DEBUG print
                print(audio_file_dict_wav)
                # store the audiofile name and the absolute path to the mp3-audiofile into the mp3-dictionary
                audio_file_dict_mp3[fl_split] = fl
                # DEBUG print
                print(audio_file_dict_mp3)

            # insert the audiofile name into the songbox
            songbox.insert(END, fl_split)


# function to save one audio file
def save_audiofile():
    # get the active, user selected audio file from the songbox
    audio_selected = songbox.get(ACTIVE)
    # get the absolute path from the active, user selected audio file
    audio_save = audio_file_dict_mp3[audio_selected]

    # open and show the file manager for the saving-process - the default extension is mp3
    file = filedialog.asksaveasfile(mode='w', defaultextension=".mp3")
    # DEBUG print
    print(file.name)

    # if the selected audio file has a wav format
    if audio_save.split(".")[-1] == "wav":
        # if the audio file should be saved as a wav file
        if file.name.split(".")[-1] == "wav":
            # export audio file as a wav file
            AudioSegment.from_wav(audio_save).export(file.name, format="wav")
        # if the audio file should be saved as a mp3 file
        elif file.name.split(".")[-1] == "mp3":
            # export audio file as a mp3 file
            AudioSegment.from_wav(audio_save).export(file.name, format="mp3")
    # if the selected audio file has a mp3 format
    elif audio_save.split(".")[-1] == "mp3":
        # if the audio file should be saved as a wav file
        if file.name.split(".")[-1] == "wav":
            # export audio file as a wav file
            AudioSegment.from_mp3(audio_save).export(file.name, format="wav")
        # if the audio file should be saved as a mp3 file
        elif file.name.split(".")[-1] == "mp3":
            # export audio file as a mp3 file
            AudioSegment.from_mp3(audio_save).export(file.name, format="mp3")


# function to pause and resume the audio player - will be triggered from the pause/resume button
def toggle():
    # get the global variables
    global paused
    # if the text of the toggle button shows Pause
    if toggle_btn["text"] == "Pause":
        # set the global variable to True
        paused = True
        # pause the audio player
        pygame.mixer.music.pause()
        # change the text of the toggle button to Resume
        toggle_btn["text"] = "Resume"
        # DEBUG print
        print("Clicked on Pause")
    # if the text of the toggle button shows Resume
    elif toggle_btn["text"] == "Resume":
        # set the global variable to False
        paused = False
        # resume the audio player
        pygame.mixer.music.unpause()
        # change the text of the toggle button to Pause
        toggle_btn["text"] = "Pause"
        # DEBUG print
        print("Clicked on Resume")


# function to start the audio player - will be triggered from the play button
def play():
    # get the global variables
    global stopped, paused, audio, cur_sel

    # if the audio player is busy or the global variable paused is true - when the audio player is busy or paused
    if pygame.mixer.music.get_busy() or paused:
        # stop the audio player
        pygame.mixer.music.stop()
        # set the global variable to True
        stopped = True
        # wait 1 second to ensure that the play_time function will be terminated in all cases
        time.sleep(1)

    # get the active, user selected audio file from the songbox
    audio_selected = songbox.get(ACTIVE)
    # get the absolute path from the active, user selected audio file
    audio = audio_file_dict_mp3[audio_selected]
    # DEBUG print
    print(audio)

    # get the current selection from the songbox and store it into the global variable
    cur_sel = songbox.curselection()[0]
    # load the audio file which has been selected by the user
    pygame.mixer.music.load(audio)
    # start the audio player without loops and at the beginning of the audio file
    pygame.mixer.music.play(loops=0, start=0)
    # set/reset the audio slider to start
    audio_slider.config(value=0)
    # set/reset the audio slider label to 00:00:00
    audio_slider_label.config(text=f'00:00:00')
    # set/reset the status bar to Time elapsed: 00:00:00 of 00:00:00
    status_bar.config(text=f"Time elapsed: 00:00:00 of 00:00:00")

    # set the global variables stopped and paused to False
    stopped = False
    paused = False

    # call the play_time function
    play_time()

    # change the text of the toggle button to Pause
    toggle_btn["text"] = "Pause"
    # DEBUG print
    print("Clicked on Play")


# function to stop the audio player  - will be triggered from the stop button and when song will be removed
def stop():
    # get the global variables
    global stopped

    # reset the status bar to a empty row
    status_bar.config(text='')
    # reset the audio slider to start
    audio_slider.config(value=0)
    # reset the audio slider label to 00:00:00
    audio_slider_label.config(text=f'00:00:00')

    # stop the audio player
    pygame.mixer.music.stop()
    # remove the active selection within the songbox
    songbox.selection_clear(ACTIVE)
    # set the global variable stopped to True
    stopped = True

    # change the text of the toggle button to Pause
    toggle_btn["text"] = "Pause"
    # DEBUG print
    print("Clicked on Stop")


# function to play the previous song in the songbox - will be triggered from the reverse button
def last_song():
    # get the global variables
    global cur_sel, audio

    # check if the current selection is the first audio file in the songbox
    if cur_sel == 0:
        # print error message and return the function
        print("Current audio is the first audio file in the songbox.")
        return
    else:
        # set the global variable cur_sel minus one
        cur_sel = cur_sel - 1
    # reset the status bar to a empty row
    status_bar.config(text='')
    # reset the audio slider to start
    audio_slider.config(value=0)
    # get the previous audio file from the songbox
    song = songbox.get(cur_sel)
    # get the absolute path from the dictionary for the previous song
    audio = audio_file_dict_mp3[song]
    # DEBUG print
    print(audio)
    # load the audio file which has been selected by the user
    pygame.mixer.music.load(audio)
    # start the audio player without loops and at the beginning of the audio file
    pygame.mixer.music.play(loops=0, start=0)

    # change the text of the toggle button to Pause
    toggle_btn["text"] = "Pause"
    # DEBUG print
    print("Clicked on Previous")

    # remove the active selection within the songbox
    songbox.selection_clear(0, END)
    # activate the previous song within the songbox
    songbox.activate(cur_sel)
    # set the active selection to the previous song
    songbox.selection_set(cur_sel, last=None)


# function to play the next song in the songbox - will be triggered from the forward button
def next_song():
    # get the global variables
    global cur_sel, audio, songbox

    # DEBUG print
    # 'end' - Indicates the end of the listbox. For most commands this refers to the last element in the listbox,
    # but for a few commands such as index and insert it refers to the element just after the last one.
    print("last songbox index", songbox.index('end'))
    # check if the current selection is the last audio file in the songbox
    if cur_sel == songbox.index('end') - 1:
        # print error message and return the function
        print("Current audio is the last audio file in the songbox.")
        return
    else:
        # set the global variable cur_sel plus one
        cur_sel = cur_sel + 1
    # reset the status bar to a empty row
    status_bar.config(text='')
    # reset the audio slider to start
    audio_slider.config(value=0)
    # get the previous audio file from the songbox
    song = songbox.get(cur_sel)
    # get the absolute path from the dictionary for the previous song
    audio = audio_file_dict_mp3[song]
    # DEBUG print
    print(audio)
    # load the audio file which has been selected by the user
    pygame.mixer.music.load(audio)
    # start the audio player without loops and at the beginning of the audio file
    pygame.mixer.music.play(loops=0, start=0)

    # change the text of the toggle button to Pause
    toggle_btn["text"] = "Pause"
    # DEBUG print
    print("Clicked on Forward")

    # remove the active selection within the songbox
    songbox.selection_clear(0, END)
    # activate the previous song within the songbox
    songbox.activate(cur_sel)
    # set the active selection to the previous song
    songbox.selection_set(cur_sel, last=None)


# function to remove a audio file from the songbox
def remove_audiofile_one():
    # get the active audio file from the songbox
    del_song = songbox.get(ACTIVE)
    # DEBUG print
    print(del_song)
    # call the stop function
    stop()
    # remove the active audio file from the songbox
    songbox.delete(ANCHOR)
    # remove the active audio file from the mp3-dictionary
    audio_file_dict_mp3.pop(del_song, None)
    # remove the active audio file from the wav-dictionary
    audio_file_dict_wav.pop(del_song, None)
    # DEBUG print
    print("Clicked on Delete one")


# function to remove all audio files from the songbox
def remove_audiofile_all():
    # call the stop function
    stop()
    # remove the all audio files from the songbox
    songbox.delete(0, END)
    # remove the all audio files from the mp3-dictionary
    audio_file_dict_mp3.clear()
    # remove the all audio files from the wav-dictionary
    audio_file_dict_wav.clear()
    # DEBUG print
    print("Clicked on Delete all")


# function which will be called by play function to move the slider and update the audio slider label and the status bar
def play_time():
    # get the global variables
    global audio, song_length, converted_audio_length

    # if stopped is True, return the function to break the after-loop
    if stopped:
        return

    # get the current play time of the audio player in milliseconds
    current_time = pygame.mixer.music.get_pos() / 1000
    # convert the current time into a '00:00:00' format
    converted_current_time = time.strftime('%H:%M:%S', time.gmtime(current_time))
    # if the selected audio file has a mp3 format
    if audio.split(".")[-1] == "mp3":
        # open the audio file
        song_mut = MP3(audio)
        # get the audio file length in seconds
        song_length = song_mut.info.length
    # if the selected audio file has a wav format
    elif audio.split(".")[-1] == "wav":
        # open the audio file
        with audioread.audio_open(audio) as f:
            # get the audio file length in seconds
            song_length = f.duration

    # convert the audio file length into a '00:00:00' format
    converted_audio_length = time.strftime('%H:%M:%S', time.gmtime(song_length))
    # increase current time by 1 second for the slider
    current_time += 1

    # if the audio slider is at the end of the audio file
    if int(audio_slider.get()) == int(song_length):
        # update the status bar
        status_bar.config(text=f"Time elapsed: {converted_audio_length} of {converted_audio_length}")
    # if the global variable paused is True
    elif paused:
        # pass the if-else condition to prevent, that the slider continue to move
        pass
    # if the audio slider has the same time as the current time - the slider has not been moved by the user
    elif int(audio_slider.get()) == int(current_time):
        # get the song length as integer
        slider_position = int(song_length)
        # update the audio slider to the new position (next second)
        audio_slider.config(to=slider_position, value=int(current_time))
        # update the status bar
        status_bar.config(text=f"Time elapsed: {converted_current_time} of {converted_audio_length}")
    # if the audio slider has been moved and it has no the same time as the current time
    else:
        # get the song length as integer
        slider_position = int(song_length)
        # update the audio slider to the new position
        audio_slider.config(to=slider_position, value=int(audio_slider.get()))
        # increase the time of the audio slider with 1 for the current song position
        next_time = int(audio_slider.get()) + 1
        # update the audio slider position value to current audio file position
        audio_slider.config(value=int(next_time))

        # convert the current audio file position into a '00:00:00' format
        converted_current_time = time.strftime('%H:%M:%S', time.gmtime(int(audio_slider.get())))

        # update the status bar
        status_bar.config(text=f"Time elapsed: {converted_current_time} of {converted_audio_length}")

        # update the audio slider label
        audio_slider_label.config(text=f'{converted_current_time}')

    # recall the play_time function every 1 second
    status_bar.after(1000, play_time)


# function that plays the audio player according to the position of the audio slider - get triggered by the audio slider
def slider(x):
    # get the global variables
    global audio, paused, stopped
    # DEBUG print
    print(audio)
    # load the audio file which has been selected by the user
    pygame.mixer.music.load(audio)
    # start the audio player without loops and at the position of the audio slider
    pygame.mixer.music.play(loops=0, start=int(audio_slider.get()))
    # if the global variable paused is True
    if paused:
        # pause the audio player
        pygame.mixer.music.pause()
    # if the global variable paused is False
    else:
        pass


# function to set the audio player x seconds back - get triggered by the xs back button
def back_x_s():
    # get the global variables
    global song_length, reverse, converted_audio_length
    # if the played time minus the x seconds is greater or equal 0
    if int(audio_slider.get()) - int(reverse.get()) >= 0:
        # set the audio player to the position played time - x seconds
        pygame.mixer.music.set_pos(int(audio_slider.get()) - int(reverse.get()))
        # update the audio slider to the position played time - x seconds
        audio_slider.config(value=int(audio_slider.get()) - int(reverse.get()))
    # if the played time minus x seconds is lower than 0
    else:
        # set the audio player back to start
        pygame.mixer.music.set_pos(0)
        # update the audio slider to start
        audio_slider.config(value=0)

    # convert the current audio file position into a '00:00:00' format
    converted_current_time = time.strftime('%H:%M:%S', time.gmtime(int(audio_slider.get())))
    # update the status bar
    status_bar.config(text=f"Time elapsed: {converted_current_time} of {converted_audio_length}")
    # update the audio slider label
    audio_slider_label.config(text=f'{converted_current_time}')


# function to set the audio player x seconds forward - get triggered by the xs forward button
def forward_x_s():
    # get the global variables
    global song_length, forward, converted_audio_length
    # if the played time plus the x seconds is lower or equal of the audio file length
    if song_length >= int(audio_slider.get()) + int(forward.get()):
        # set the audio player to the position played time + x seconds
        pygame.mixer.music.set_pos(int(audio_slider.get()) + int(forward.get()))
        # update the audio slider to the position played time + x seconds
        audio_slider.config(value=int(audio_slider.get()) + int(forward.get()))
    # if the played time plus x seconds is greater than the audio file length
    else:
        # set the audio player forward to the end of the audio file
        pygame.mixer.music.set_pos(int(song_length))
        # update the audio slider to the end
        audio_slider.config(value=int(song_length))

    # convert the current audio file position into a '00:00:00' format
    converted_current_time = time.strftime('%H:%M:%S', time.gmtime(int(audio_slider.get())))
    # update the status bar
    status_bar.config(text=f"Time elapsed: {converted_current_time} of {converted_audio_length}")
    # update the audio slider label
    audio_slider_label.config(text=f'{converted_current_time}')


# function to change the text on the forward button - get triggered by the menu bar / audio
def forward_second_change():
    # get the global variables
    global forward
    # change the text on the forward button according to the configuration in the menu bar / audio
    forward_10s_btn.config(text=f"{forward.get()}s forward")


# function to change the text on the back button - get triggered by the menu bar / audio
def reverse_second_change():
    # get the global variables
    global reverse
    # change the text on the back button according to the configuration in the menu bar / audio
    back_10s_btn.config(text=f"{reverse.get()}s back")


# function to print the current count of active threads
def Threadcount():
    # print the current count of active threads
    print(threading.active_count())


# function to reset the vertical lines, the textBox and the audio wave viewer
def Reset():
    # get the global variables
    global pos_1, pos_2, duration
    # DEBUG print
    print("Cursor")
    # focus the UI to the audio wave viewer
    top.focus()
    # DEBUG print
    print("Pos_1:", pos_1)
    # DEBUG print
    print("Pos_2:", pos_2)

    try:
        # if the global variable pos_1 is True (the position_1 vertical line is set)
        if pos_1:
            # remove the position_1 vertical line
            position_1.remove()
            # set the global variable pos_1 to False
            pos_1 = False
        # if the global variable pos_2 is True (the position_2 vertical line is set)
        if pos_2:
            # remove the position_2 vertical line
            position_2.remove()
            # set the global variable pos_2 to False
            pos_2 = False

        # clear textBox
        textBox.delete(1.0, END)
        # reset audio wave viewer and set the x-limitation from 0 to the audio file length
        ax_1.set_xlim(0, duration)
    # exception handling
    except Exception as e:
        # print exception
        print("Hops : ", e)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# function to create the audio wave viewer - will be called in the main function
def create_audioviewer():
    # get the global variables
    global go_to_x_position, go_to_x_zoom, time_plot, ax_1, canvas, toolbar, \
        get_to_position_1, get_to_position_2, lines, duration, script_dir

    # create the audio wave viewer figure
    fig = Figure(figsize=(3, 2.20), dpi=100)
    # relative path to the first wav file, which will be plotted
    file_path = 'audio/Start_wave_file.wav'
    # create the absolute path to the first wav file
    abs_file_path = os.path.join(script_dir, file_path)
    # DEBUG print
    print(abs_file_path)
    # read the wav file
    sampleRate, audioBuffer = scipy.io.wavfile.read(abs_file_path)
    # get the duration of the audio file
    duration = len(audioBuffer) / sampleRate
    # create a time vector to get the values for the x-axis
    time_plot = np.arange(0, duration, 1 / sampleRate)
    # add an subplot to the figure
    ax_1 = fig.add_subplot()
    # plot the first audio wave from the first wav file
    lines = ax_1.plot(time_plot, audioBuffer[:, 0], c="black")
    # set the visibility of the x- and the y-axis to False
    ax_1.axes.get_yaxis().set_visible(False)
    # set the visibility of the top border to False
    ax_1.spines['top'].set_visible(False)
    # set the visibility of the right border to False
    ax_1.spines['right'].set_visible(False)
    # set the visibility of the left border to False
    ax_1.spines['left'].set_visible(False)
    # add a label to the x-axis
    ax_1.set_xlabel('Time [s]')

    try:
        # try to set the layout of the figure to tight
        fig.set_tight_layout('tight')
    # exception handling
    except Exception as e:
        # print exception
        print("Hops : ", e)

    # create a drawing area for the audio wave viewer
    canvas = FigureCanvasTkAgg(fig, master=root)
    # draw the drawing area
    canvas.draw()

    # connect events to the keyboard
    # canvas.mpl_connect("key_press_event", lambda event: print(f"you pressed {event.key}"))
    # canvas.mpl_connect("key_press_event", key_press_handler)

    # add the navigation toolbar to the audio wave viewer
    toolbar = NavigationToolbar2Tk(canvas, root, pack_toolbar=False)
    # update the navigation toolbar
    toolbar.update()

    # pack the audio wave viewer to the top
    canvas.get_tk_widget().pack(in_=top, side=TOP, fill=BOTH, expand=True)
    # pack the navigation toolbar to the audio wave viewer
    toolbar.pack(in_=top, side=TOP, fill=X)

    # initialize the integration into the toolbar row in order of appearance, left to right:
    # create a label
    set_x_position = Label(root)
    # pack it into the navigation toolbar row
    set_x_position.pack(in_=toolbar, side=LEFT)
    # set the text of the label to "X_Position :"
    set_x_position['text'] = " X_Position : "

    # create an entry
    go_to_x_position = Entry(root, width=6, justify="right")
    # pack it into the navigation toolbar row
    go_to_x_position.pack(in_=toolbar, side=LEFT)
    # set the half of the duration as the initial value
    go_to_x_position.insert(0, float("{:.2f}".format(duration / 2)))

    # create a label
    set_zoom = Label(root)
    # pack it into the navigation toolbar row
    set_zoom.pack(in_=toolbar, side=LEFT)
    # set the text of the label to "X_Zoom :"
    set_zoom['text'] = " X_Zoom : "

    # create an entry
    go_to_x_zoom = Entry(root, width=6, justify="right")
    # pack it into the navigation toolbar row
    go_to_x_zoom.pack(in_=toolbar, side=LEFT)
    # set 0.0 as the initial value
    go_to_x_zoom.insert(0, "0.0")

    # create a label
    set_position_1 = Label(root)
    # pack it into the navigation toolbar row
    set_position_1.pack(in_=toolbar, side=LEFT)
    # set the text of the label to "Position_1 :"
    set_position_1['text'] = " Position_1 : "

    # create an entry
    get_to_position_1 = Entry(root, width=6, justify="right")
    # pack it into the navigation toolbar row
    get_to_position_1.pack(in_=toolbar, side=LEFT)
    # set 0.0 as the initial value
    get_to_position_1.insert(0, "0.0")

    # create a label
    set_position_2 = Label(root)
    # pack it into the navigation toolbar row
    set_position_2.pack(in_=toolbar, side=LEFT)
    # set the text of the label to "Position_2 :"
    set_position_2['text'] = " Position_2 : "

    # create an entry
    get_to_position_2 = Entry(root, width=6, justify="right")
    # pack it into the navigation toolbar row
    get_to_position_2.pack(in_=toolbar, side=LEFT)
    # set 0.0 as the initial value
    get_to_position_2.insert(0, "0.0")

    # create a speech-to-text button, which will call the STT_function function when pressed
    STT_btn = Button(root, text="Speech-to-Text Algorithm", width=18, command=STT_function)
    # pack it into the navigation toolbar row
    STT_btn.pack(in_=toolbar, side=LEFT)

    # create a reset button, which will call the Reset function when pressed
    Reset_btn = Button(root, text="Reset", width=5, command=Reset)
    # pack it into the navigation toolbar row
    Reset_btn.pack(in_=toolbar, side=LEFT)

    # bind the key enter to marks the end of the entry for the entry boxes above
    go_to_x_position.bind("<Return>", gototf_Return)
    go_to_x_zoom.bind("<Return>", zoomtf_Return)
    get_to_position_1.bind("<Return>", position_1_vertical_line)
    get_to_position_2.bind("<Return>", position_2_vertical_line)


# function to update the audio wave viewer if a new audio file will be loaded
def update_wave_viewer(self):
    # get the global variables
    global time_plot, lines, duration, pos_1, pos_2

    try:
        # get the active, user selected audio file from the songbox
        audio_selected = songbox.get(ACTIVE)
        # get the absolute path from the active, user selected audio file
        audio_update = audio_file_dict_wav[audio_selected]
        # read the wav file
        sampleRate, audioBuffer = scipy.io.wavfile.read(audio_update)
        # get the duration of the audio file
        duration = len(audioBuffer) / sampleRate
        # create a time vector to get the values for the x-axis
        time_plot = np.arange(0, duration, 1 / sampleRate)  # time vector

        # Optional: overlaying multiple audio waves
        # get the previous wave plot
        line_1 = lines.pop(0)
        # remove the previous wave plot
        line_1.remove()
        # plot the new audio wave
        lines = ax_1.plot(time_plot, audioBuffer[:, 0], c="black")
        # set the x-limitations of the audio wave viewer from 0 to the audio file length
        ax_1.set_xlim(0, duration)

        # if the global variable pos_1 is True (the position_1 vertical line is set)
        if pos_1:
            # remove the position_1 vertical line
            position_1.remove()
            # set the global variable pos_1 to False
            pos_1 = False
        # if the global variable pos_2 is True (the position_2 vertical line is set)
        if pos_2:
            # remove the position_2 vertical line
            position_2.remove()
            # set the global variable pos_2 to False
            pos_2 = False

    # exception handling
    except Exception as e:
        # print exception
        print("Hops : ", e)

    # put a "update"-message into the queue for the thread to update the subplot
    client.queue.put("update")


# change the available STT algorithms based on the chosen language
def language_change():
    # get the global variables
    global language, STTMenu
    # check which language was chosen
    if int(language.get()) == 0:
        # English
        # disable/enable the STT algorithms based on the availability in the chosen language
        STTMenu.entryconfig("Google Speech Recognition", state="normal")
        STTMenu.entryconfig("IBM Speech To Text", state="normal")
        STTMenu.entryconfig("Google Cloud Speech API", state="normal")
        STTMenu.entryconfig("Wit.ai", state="normal")
        STTMenu.entryconfig("CMUSphinx", state="normal")
        STTMenu.entryconfig("Houndify API", state="normal")

    elif int(language.get()) == 1:
        # German
        # disable/enable the STT algorithms based on the availability in the chosen language
        STTMenu.entryconfig("Google Speech Recognition", state="normal")
        STTMenu.entryconfig("IBM Speech To Text", state="normal")
        STTMenu.entryconfig("Google Cloud Speech API", state="normal")
        STTMenu.entryconfig("Wit.ai", state="normal")
        #STTMenu.entryconfig("CMUSphinx", state="disabled")
        STTMenu.entryconfig("Houndify API", state="disabled")

def color():
    picked_color = colorchooser.askcolor()[1]

    if picked_color:
        color_font = font.Font(textBox, textBox.cget("font"))
        var = f"colored_{picked_color}"
        # configure a tag
        textBox.tag_config(var, font=color_font, foreground=picked_color)
        #textBox.tag_config("colored"+"_"+str(picked_color), font=color_font, foreground=picked_color)

        # define current tags
        current_tags = textBox.tag_names("sel.first")

        print(current_tags)

        if "colored" in current_tags:
            matching = [s for s in current_tags if "colored" in s]
            textBox.tag_remove(matching, "sel.first", "sel.last")
            textBox.tag_add(var, "sel.first", "sel.last")
        else:
            textBox.tag_add(var, "sel.first", "sel.last")

# main function
# ----------------------------------------------------------------------#
# get the absolute path to the main directory
script_dir = os.path.dirname(__file__)  # <-- absolute dir the script is in
# define the relative path for the location of the icon image
file_path_icon = 'images/transcription_icon.png'
# create the absolute path to the location of the icon image
abs_file_path_icon = os.path.join(script_dir, file_path_icon)

# initialize the tkinter toplevel widget
root = Tk()
# define the title of the application
root.title('Simple Transcription Editor')
# add the icon image to the application
root.iconphoto(False, PhotoImage(file=abs_file_path_icon))
# define the initial size of the application
root.geometry('1280x960')
# define the minimum size of the application
root.minsize(1280, 960)
# allowing root window to change it's size according to user's need
root.resizable(True, True)

# global variables for user interface

# define the initial value for forward the audio player
forward = IntVar(value=10)
# define the initial value for backward the audio player
reverse = IntVar(value=10)
# define the initial value for selecting the speech-to-text algorithm
stt_algorithm = IntVar(value=0)
# define the initial value for selecting if the whole audio file or only a audio snippet should be transcribed
stt_config = IntVar(value=0)
# define the initial value for selecting in which language is the audio file for the transcription
language = IntVar(value=0)

# user interface

# define a top frame
top = Frame(root)
# pack the top frame on the top of the user interface
top.pack(side=TOP, fill='both', padx=5, pady=5)
# define a left frame
left = Frame(root)
# pack the left frame on the left side of the user interface
left.pack(side=LEFT, padx=5, pady=5)
# define a right frame
right = Frame(root)
# pack the right frame on the right side of the user interface
right.pack(side=RIGHT, fill='both', expand=True, pady=5)
# define a left_top frame inside the left frame
left_top = Frame(left)
# pack the left_top frame on the top of the left frame
left_top.pack(side=TOP)
# define a left_center frame inside the left frame
left_center = Frame(left)
# pack the left_center frame below the left_top frame
left_center.pack()
# define a left_bottom frame inside the left frame
left_bottom = Frame(left)
# pack the left_bottom frame below the left_center frame
left_bottom.pack()
# define a left_status_bar frame inside the left frame
left_status_bar = Frame(left)
# pack the left_status_bar frame on the bottom of the left frame
left_status_bar.pack(side=BOTTOM)

# create a label - Audio Controller
label2 = Label(root, text='Audio Controller')
# pack the label on the top of the left_top frame
label2.pack(in_=left_top, side='top', fill='both')
# create a listbox
songbox = Listbox(root, width=25)
# pack the listbox below the Audio Controller label in the left_top frame
songbox.pack(in_=left_top, side='top', fill="both")

# create a label - Music Slider Label
audio_slider_label = Label(root, text='00:00:00', bd=1, width=28)
# pack the label below the listbox in the left_top frame
audio_slider_label.pack(in_=left_top, side='top', fill=X, pady=5)

# create a scale - Music Position Slider
audio_slider = ttk.Scale(root, from_=0, to=100, orient=HORIZONTAL, value=0, command=slider)
# pack the scale below the Music Slider Label in the left_top frame
audio_slider.pack(in_=left_top, side='top', fill='both', pady=5, padx=10)

# create a back x seconds button, which will call the back_x_s function when pressed
back_10s_btn = Button(root, text="10s back", width=11, command=back_x_s)
# pack the button below the Music Position Slider on the left side in the left_top frame
back_10s_btn.pack(in_=left_top, side='left', fill='both')
# create a forward x seconds button, which will call the forward_x_s function when pressed
forward_10s_btn = Button(root, text="10s forward", width=11, command=forward_x_s)
# pack the button below the Music Position Slider next to the back x seconds button in the left_top frame
forward_10s_btn.pack(in_=left_top, side='left', fill='both')
# create a reverse button, which will call the last_song function when pressed
reverse_btn = Button(root, text="Reverse", command=last_song)
# pack the button below the forward and back x seconds buttons on the left side in the left_center frame
reverse_btn.pack(in_=left_center, side='left', fill='both')
# create a toggle button, which will call the toggle function when pressed
toggle_btn = Button(root, text="Pause", width=6, command=toggle)
# pack the button below the forward and back x seconds buttons next to the reverse button in the left_center frame
toggle_btn.pack(in_=left_center, side='left', fill='both')
# create a forward button, which will call the next_song function when pressed
forward_btn = Button(root, text="Forward", command=next_song)
# pack the button below the forward and back x seconds buttons next to the toggle button in the left_center frame
forward_btn.pack(in_=left_center, side='left', fill='both')
# create a play button, which will call the play function when pressed
play_btn = Button(root, text="Play", width=11, command=play)
# pack the button below the forward, toggle and back buttons on the left side in the left_bottom frame
play_btn.pack(in_=left_bottom, side='left', fill='both', expand=True)
# create a stop button, which will call the stop function when pressed
stop_btn = Button(root, text="Stop", width=11, command=stop)
# pack the button below the forward, toggle and back buttons next to the play button in the left_bottom frame
stop_btn.pack(in_=left_bottom, side='left', fill='both', expand=True)
# create a scrolledText entry
textBox = ScrolledText(root, font=("Times New Roman", 16), )
# pack the scrolledText entry in the right frame
textBox.pack(in_=right, side='top', fill="both", expand=1)
# create a label - Status Bar
status_bar = Label(root, text='', bd=1, relief=GROOVE, width=29)
# pack the button below the play and stop buttons in the left_status_bar frame
status_bar.pack(in_=left_status_bar, side='bottom', fill=X, pady=10, )

# create a main menu
menubar = Menu(root)
# add the menu to the user interface
root.config(menu=menubar)

# create a submenu - AudiofileMenu
AudiofileMenu = Menu(menubar)
# add a command to the AudiofileMenu, which calls the open_audiofile_one function when clicked
AudiofileMenu.add_command(label="Open audiofile", command=open_audiofile_one)
# add a command to the AudiofileMenu, which calls the open_audiofile_multiple function when clicked
AudiofileMenu.add_command(label="Open multiple audiofiles", command=open_audiofile_multiple)
# add an separator to the AudiofileMenu
AudiofileMenu.add_separator()
# add a command to the AudiofileMenu, which calls the remove_audiofile_one function when clicked
AudiofileMenu.add_command(label="Remove audiofile", command=remove_audiofile_one)
# add a command to the AudiofileMenu, which calls the remove_audiofile_all function when clicked
AudiofileMenu.add_command(label="Remove all audiofiles", command=remove_audiofile_all)
# add an separator to the AudiofileMenu
AudiofileMenu.add_separator()
# add a command to the AudiofileMenu, which calls the save_audiofile function when clicked
AudiofileMenu.add_command(label="Save audiofile", command=save_audiofile)
# add the submenu to the main menu
menubar.add_cascade(label="Audio file", menu=AudiofileMenu)

# create a submenu - TextfileMenu
TextfileMenu = Menu(menubar)
# add a command to the TextfileMenu, which calls the onopen function when clicked
TextfileMenu.add_command(label="Open", command=onopen)
# add a command to the TextfileMenu, which calls the save_command function when clicked
TextfileMenu.add_command(label="Save", command=save_command)
# add the submenu to the main menu
menubar.add_cascade(label="Text file", menu=TextfileMenu)

# create a submenu - AudioMenu
AudioMenu = Menu(menubar)
# add a command to the AudioMenu, without function
AudioMenu.add_command(label="Forward")
# disable the Forward command in the AudioMenu
AudioMenu.entryconfig("Forward", state="disabled")
# add a radiobutton to the AudioMenu, which calls the forward_second_change function when clicked
# and changes the value of the variable forward to 5
AudioMenu.add_radiobutton(label="5 seconds", variable=forward, value=5, command=forward_second_change)
# add a radiobutton to the AudioMenu, which calls the forward_second_change function when clicked
# and changes the value of the variable forward to 10
AudioMenu.add_radiobutton(label="10 seconds", variable=forward, value=10, command=forward_second_change)
# add an separator to the AudioMenu
AudioMenu.add_separator()
# add a command to the AudioMenu, without function
AudioMenu.add_command(label="Back")
# disable the Back command in the AudioMenu
AudioMenu.entryconfig("Back", state="disabled")
# add a radiobutton to the AudioMenu, which calls the reverse_second_change function when clicked
# and changes the value of the variable reverse to 5
AudioMenu.add_radiobutton(label="5 seconds", variable=reverse, value=5, command=reverse_second_change)
# add a radiobutton to the AudioMenu, which calls the reverse_second_change function when clicked
# and changes the value of the variable reverse to 10
AudioMenu.add_radiobutton(label="10 seconds", variable=reverse, value=10, command=reverse_second_change)
# add the submenu to the main menu
menubar.add_cascade(label="Audio", menu=AudioMenu)

# create a submenu - STTMenu
STTMenu = Menu(menubar)
# add a command to the STTMenu, without function
STTMenu.add_command(label="Speech-to-Text Algorithm")
# disable the Speech-to-Text Algorithm command in the STTMenu
STTMenu.entryconfig("Speech-to-Text Algorithm", state="disabled")
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 0
STTMenu.add_radiobutton(label="Google Speech Recognition", variable=stt_algorithm, value=0)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 1
STTMenu.add_radiobutton(label="IBM Speech To Text", variable=stt_algorithm, value=1)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 2
STTMenu.add_radiobutton(label="Google Cloud Speech API", variable=stt_algorithm, value=2)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 3
STTMenu.add_radiobutton(label="Wit.ai", variable=stt_algorithm, value=3)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 4
STTMenu.add_radiobutton(label="CMUSphinx", variable=stt_algorithm, value=4)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_algorithm to 5
STTMenu.add_radiobutton(label="Houndify API", variable=stt_algorithm, value=5)
# add an separator to the STTMenu
STTMenu.add_separator()
# add a command to the STTMenu, without function
STTMenu.add_command(label="STT Configuration")
# disable the STT Configuration command in the STTMenu
STTMenu.entryconfig("STT Configuration", state="disabled")
# add a radiobutton to the STTMenu, which changes the value of the variable stt_config to 0
STTMenu.add_radiobutton(label="complete audio file", variable=stt_config, value=0)
# add a radiobutton to the STTMenu, which changes the value of the variable stt_config to 1
STTMenu.add_radiobutton(label="selected audio snippet", variable=stt_config, value=1)
# add the submenu to the main menu
menubar.add_cascade(label="STT Algorithm", menu=STTMenu)

# create a submenu - LanguageMenu
LanguageMenu = Menu(menubar)
# add a radiobutton to the STTMenu, which changes the value of the variable language to 0
LanguageMenu.add_radiobutton(label="English", variable=language, value=0, command=language_change)
# add a radiobutton to the STTMenu, which changes the value of the variable language to 1
LanguageMenu.add_radiobutton(label="German", variable=language, value=1, command=language_change)
# Optional: add more languages
# add the submenu to the main menu
menubar.add_cascade(label="Language", menu=LanguageMenu)

# create a submenu - DebugMenu
DebugMenu = Menu(menubar)
# add a command to the DebugMenu, which calls the Threadcount function when clicked
DebugMenu.add_command(label="Nr. of Threads", command=Threadcount)

DebugMenu.add_command(label="Color", command=color)

# add the submenu to the main menu
menubar.add_cascade(label="Debug", menu=DebugMenu)

# call the create_audioviewer function to create the audio wave viewer on the top of the user interface
create_audioviewer()
# bind the double click in the songbox to call the update_wave_viewer function and update the wave viewer
songbox.bind('<Double-Button>', update_wave_viewer)

# create a instance of the ThreadedClient class and start a thread to update the audio wave viewer
client = ThreadedClient(root)

# call the mainloop of the tkinter toplevel widget
root.mainloop()
