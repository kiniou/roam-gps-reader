#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from sys import argv, exit, stdout
from pprint import pprint, pformat
from optparse import OptionParser

import ConfigParser


from OpenGL.GL import *
from OpenGL.GLU import *

from math import * # trigonometry

import pygame # just to get a display

import time
import datetime

import json
import urllib, httplib

import multiprocessing
from multiprocessing import Process, Pipe, Queue, Event
from multiprocessing import freeze_support
from Queue import Empty as QEmpty
import logging


__version__ = "0.1"

__options__ = None
__args__ = None


screen_size = (500,400)

console_font = None
app_texts = {
	'point' : ['.',None,None],
	'acquire':['Acquiring GPS Data',None,None],
	'processing':['New Data Incoming',None,None],
	'locations':['No Locations',None,None],
	'status':['No Status',None,None],
}

def CreateFont():
			global console_font
			font_name = 'datas/segao_2.ttf'
			console_font = pygame.font.Font(font_name,int(float(screen_size[1]/30.0)))
			#console_font.set_bold(True)
			for k in app_texts:
				BuildText(app_texts[k])

def BuildText(text):
	global console_font
	if (text[0] is not None):
		print "Building %s" % (text[0])
		#text_surf = console_font.render(text[0],False,(255,255,255))
		text_surf = console_font.render(text[0],False,(0,0,0))
		text[1] = pygame.image.tostring(text_surf , 'RGBA', True)
		text[2] = (text_surf.get_size())
	

def BeginTextView():
	w = screen_size[0]
	h = screen_size[1]
	glMatrixMode(GL_PROJECTION)
	glLoadIdentity()
	glOrtho(0.0, w - 1.0, 0.0, h - 1.0, -1.0, 1.0)


def Begin3dView():
	w = screen_size[0]
	h = screen_size[1]
	glMatrixMode(GL_PROJECTION)
	glLoadIdentity()
	gluPerspective(120.0, float(w) / float(h), 0.5, 1000.0)


def HTMLColorToRGB(colorstring):
    """ convert #RRGGBB to an (R, G, B) tuple """
    colorstring = colorstring.strip()
    if colorstring[0] == '#': colorstring = colorstring[1:]
    if len(colorstring) != 6:
        raise ValueError, "input #%s is not in #RRGGBB format" % colorstring
    r, g, b = colorstring[:2], colorstring[2:4], colorstring[4:]
    r, g, b = [int(n, 16) for n in (r, g, b)]
    return (r/255.0, g/255.0, b/255.0)


class GPSUpdater(Process):

	def __init__(self,options,cfg_args,queue,e_stopped,e_startup):

		Process.__init__(self)
		self.sleepwait = 5.0
		self.queue = queue
		self.e_stopped = e_stopped
		self.e_startup = e_startup
		self.check_server = cfg_args['server']
		self.check_request = cfg_args['path']
		self.check_headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain" , 'cache-control':'no-cache'}
		self.http_con = httplib.HTTPConnection(self.check_server)
		self.query=""
		self.mode = 'server'
		self.filemode_data = { 'locations':[] }

		if (options is not None):
			if (hasattr(options,'file')) and (options.file is not ""):
				self.mode = 'file'
				self.sleepwait = 5.0
				try:
					f = open(options.file,'r')
				except Exception, err :
					print "File Operation failed : " , str(err)
				else :
					start_date = datetime.datetime.strptime(f.readline().strip(),"%Y-%m-%d %H:%M:%S")
					end_date = datetime.datetime.strptime(f.readline().strip(),"%Y-%m-%d %H:%M:%S")
					for i,l in enumerate(f) :
						values = l.strip().split(',')
						#print i,values
						
						v = {'longitude': values[0], 'latitude': values[1] , 'accuracy' : values[2], 'timestamp' : None}
						self.filemode_data['locations'].append(v)
					
					step = (end_date - start_date)/len(self.filemode_data['locations'])

					for i,l in enumerate(self.filemode_data['locations']):
						self.filemode_data['locations'][i]['timestamp'] = (start_date + i * step).strftime("%Y-%m-%d %H:%M:%S")
						#print self.filemode_data['locations'][i]

					#print pformat(start_date) , pformat(end_date)
					self.lastupdate = self.filemode_data['locations'][0]
					f.close()
					print "Running in file mode with %d locations" % (len(self.filemode_data['locations']))

			elif (hasattr(options,'fromdate')) and (options.fromdate is not "") :
				self.mode = 'server'
				self.lastupdate = options.fromdate
			else :
				self.mode = 'server'
				self.lastupdate = time.strftime('%Y-%m-%d %H:%M:%S')
				print 'GPS UPDATER : lastupdate %s' % self.lastupdate

#		self.get_last_coordinates()

	def run(self):
			stopped = False
			print "GPS Updater waiting for startup event"
			self.e_startup.wait()
			print "GPS Updater task : running..."

			while(not stopped):
				if   (self.mode == 'server'):
					self.get_last_server_coordinates()
				elif (self.mode == 'file'):
					self.get_last_file_coordinates()

				self.e_stopped.wait(5)
				if (self.e_stopped.is_set()) : stopped = True
				print "GPS_UPDATER status : ", not stopped , self.e_stopped.is_set()
				#time.sleep(5)

			return

	def get_last_file_coordinates(self):
			lastupdate_tmp = self.lastupdate
			if (self.lastupdate is not None) :
				if len(self.filemode_data['locations'])>0:
					result = {'result' : [self.filemode_data['locations'].pop(0)]}
					print pformat(result['result'][-1]) , len(self.filemode_data['locations'])
					#self.filemode_data['locations'][0]
					self.queue.put(result['result'])

	def get_last_server_coordinates(self):
			lastupdate_tmp = self.lastupdate
			if (self.lastupdate is not None) :
				self.check_query = urllib.urlencode( 
					{ 'query' : json.dumps( { 'fromdate' : "'%s'" % (self.lastupdate) } ) }
				)
			else :
				self.check_query = None

			try:
				self.http_con.connect()
				self.http_con.request('POST', self.check_request, self.check_query , self.check_headers)
				response = self.http_con.getresponse()
				result = json.loads(response.read())
				self.http_con.close()
			except Exception,err:
				self.http_con = httplib.HTTPConnection(self.check_server)
				print "Problem with internet connection" , pformat(err)
				result = None


			if ( result is not None and result.has_key('result') and len(result['result'])>0 ) :
				self.queue.put(result['result'])
				last_result = result['result'][-1]
				print "GPSUPDATE : %d new location(s) since %s" % (len(result['result']), self.lastupdate)
				self.lastupdate = last_result['timestamp']


#TODO : define an OpenGL worker to build VBO in parallel

if __name__ == "__main__" :

		no_data = 0

		prog_usage = "%prog [-s '2009-12-31 23:59:59']"
		prog_desc = "Roam#1 Pickup GPS Indicator"
		parser = OptionParser(usage=prog_usage,version=__version__,description=prog_desc)

		parser.add_option("-s" , "--start",
						action="store" , type="string" , dest="fromdate", default="",
						help="Start receiving (or restore older) GPS location from specific date")

		parser.add_option("-f" , "--file",
						action="store" , type="string" , dest="file", default="",
						help="Import GPS locations from file")
		(__options__, __args__) = parser.parse_args()
		print "OPTIONS : " , pformat(__options__)
		print "ARGS" , pformat(__args__)


		config = ConfigParser.ConfigParser()
		config.read('roam-gps-reader.cfg')

		if not(config.has_option('GPS WebService','server') and config.has_option('GPS WebService','path')):
			exit()
		else:
			cfg_args = {'server':config.get('GPS WebService','server') , 'path':config.get('GPS WebService','path') }

		multiprocessing.freeze_support()
		
		multiprocessing.log_to_stderr(logging.DEBUG)

		locations = []
		#screen_size = (300,300)

		#queue_locations = Queue.Queue(1024)
		queue_locations = Queue(1024)
		e_startup = Event()
		e_startup.clear()
		e_stopped = Event()
		e_stopped.clear()

		p_gps_upd = GPSUpdater(__options__ , cfg_args, queue_locations,e_stopped,e_startup)
		p_gps_upd.daemon = True

		print "MOTHER : Main Loop start"
		pygame.init()
		pygame.display.set_mode(screen_size, pygame.OPENGL|pygame.DOUBLEBUF|pygame.NOFRAME|pygame.RESIZABLE)
		glViewport(0,0,screen_size[0],screen_size[1])

		pygame.font.init()
		if (pygame.font.get_init()):
			CreateFont()
		else :
			print 'Could not render font.'
			sys.exit(0)


		#Prepare grid and sonar
		main_loop = True
		rot = 0.0
		chrono = pygame.time.get_ticks()/1000.0
		chrono_tmp = chrono
		#print "KEYDOWN" , pygame.KEYDOWN , "K_q" , pygame.K_q, "KMOD_CTRL",pygame.KMOD_CTRL,"EVENT",pformat(e)
		loc_color = HTMLColorToRGB("#30d35f")

		triangle = [ 	{'x':0,'y':0,'z':0},
						{'x':cos(radians(0)),'y':sin(radians(0)),'z':1},
						{'x':cos(radians(120)),'y':sin(radians(120)),'z':1},
						{'x':cos(radians(240)),'y':sin(radians(240)),'z':1},
					]

		circle_angle = 30
		glGenLists(4)
		glNewList(2,GL_COMPILE)
		glBegin(GL_TRIANGLES)
		for d in range(0,360,circle_angle) :
			glVertex3f(0,0,0)
			glVertex3f(cos(radians(d)) , sin(radians(d)) , 0)
			glVertex3f(cos(radians(d + circle_angle)) , sin(radians(d + circle_angle)) , 0)
		glEnd()
		glEndList()

		glNewList(1,GL_COMPILE)

		glBegin(GL_TRIANGLE_STRIP)

		glVertex3f(triangle[0]['x'] , triangle[0]['y'] , triangle[0]['z'])
		glVertex3f(triangle[1]['x'] , triangle[1]['y'] , triangle[1]['z'])
		glVertex3f(triangle[2]['x'] , triangle[2]['y'] , triangle[2]['z'])

		glVertex3f(triangle[0]['x'] , triangle[0]['y'] , triangle[0]['z'])
		glVertex3f(triangle[2]['x'] , triangle[2]['y'] , triangle[2]['z'])
		glVertex3f(triangle[3]['x'] , triangle[3]['y'] , triangle[3]['z'])

		glVertex3f(triangle[0]['x'] , triangle[0]['y'] , triangle[0]['z'])
		glVertex3f(triangle[3]['x'] , triangle[3]['y'] , triangle[3]['z'])
		glVertex3f(triangle[1]['x'] , triangle[1]['y'] , triangle[1]['z'])

		glEnd()

		glEndList()

		glNewList(3,GL_COMPILE)

		glBegin(GL_LINES)
		glVertex3f(-400,0,0)
		glVertex3f( 400,0,0) 
		glVertex3f(0,-400,0)
		glVertex3f(0, 400,0) 
		glEnd()
		glEndList()

		lookat_target = [0,0,0]
		lookat_previous = [0,0,0]
		lookat_current = [0,0,0]
		lookat_diff = [0,0,0]
		lookat_diffp = [0,0,0]
		current_location = 0

		while(main_loop):

			r_chrono = chrono - chrono_tmp
			rot += 45 * r_chrono
			if (rot>360.0) : rot -= 360.0 

			#Check Game Events
			game_events = pygame.event.get()
			for e in game_events:
				#if CTRL+Q or Exit Event are raised : exit
				if (e.type == pygame.KEYDOWN and e.key == pygame.K_q and e.mod&pygame.KMOD_CTRL) or (e.type == pygame.QUIT) : main_loop = False
				if (e.type == pygame.KEYDOWN and e.key == pygame.K_f and e.mod&pygame.KMOD_ALT):
					#screen_size = (1280,1024)
					#screen_size = (1152,864)
					screen_size = (800,480)
					pygame.display.set_mode(screen_size , pygame.OPENGL|pygame.DOUBLEBUF|pygame.NOFRAME)
					glViewport(0,0,screen_size[0],screen_size[1])
					if (pygame.font.get_init()):
						CreateFont()
					else :
						print 'Could not render font.'
					
					


			glClearColor(1.0, 1.0, 1.0, 0.1)
			glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)

			glEnable(GL_BLEND)
			glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

			Begin3dView()

			zoom = 10000

			if(len(locations)>0) :
				if 	( ( lookat_current[0] != lookat_target[0]) and (lookat_current[1] != lookat_target[1]) ) :
					x = lookat_diff[0]
					y = lookat_diff[1]
					M = sqrt(pow(x,2) + pow(y,2))
					alpha = atan2(y,x)
					inc_x = (M * cos(alpha))
					inc_y = (M * sin(alpha))

					xp = lookat_current[0] - lookat_previous[0]
					yp = lookat_current[1] - lookat_previous[1]
					Mp = sqrt(pow(xp,2) + pow(yp,2))
					if (Mp<M) :
						lookat_current[0] += inc_x * r_chrono
						lookat_current[1] += inc_y * r_chrono
					else :
						lookat_current[0] = lookat_target[0]
						lookat_current[1] = lookat_target[1]
				
					#print "TEST lookat id:%d, M:%d, Mp:%d, chrono:%f" % (current_location,M,Mp,r_chrono)
					#print lookat_previous
					#print lookat_current
					#print lookat_target
					#print lookat_diff
				else:
					if (current_location < len(locations)):
						if (current_location > 0) : lookat_previous[0:] = lookat_target[0:]
						current_location += 1
						l = locations[current_location - 1]
						lookat_target = [zoom * float(l['longitude']) , zoom * float(l['latitude']) , 0]
						lookat_diff[0] = lookat_target[0] - lookat_current[0]
						lookat_diff[1] = lookat_target[1] - lookat_current[1]
						lookat_diff[2] = lookat_target[2] - lookat_current[2]
						if (current_location == 0) : lookat_previous = lookat_target
						app_texts['locations'][0] = "%-f ' %-f~%-5.2f" % (float(l['longitude']),float(l['latitude']),float(l['accuracy']))
						BuildText(app_texts['locations'])
						status = 'No Status'
						if (l.has_key('status')):
							print "STATUS %d" % int(l['status'])
							if (int(l['status']) == 0) :
								status = 'Stopped'
							elif (int(l['status']) == 1) :
								status = 'In Movement'
							elif (int(l['status']) == 2) :
								status = 'Roaming Music'
							elif (int(l['status']) == 3) :
								status = 'PANIC !!! :P'

						app_texts['status'][0] = status
						BuildText(app_texts['status'])

						glNewList(4,GL_COMPILE)
						glBegin(GL_LINES)
						for i,l in enumerate(locations[0:current_location]):
							if (i > 0) :
								glVertex3f(zoom * float(locations[i-1]['longitude']), zoom * float(locations[i-1]['latitude']),0)
								glVertex3f(zoom * float(locations[i]['longitude']), zoom * float(locations[i]['latitude']),0)
						glEnd()
						glEndList()
			beta = 140
			alpha = rot


			Begin3dView()
#			if (len(locations)>0) :
#				l = locations[current_location-1]
#				if (int(l['status']) != 1):
#					gluLookAt(lookat_current[0] + 10 * sin(radians(alpha)) * cos(radians(beta)),lookat_current[1]+ 10 * cos(radians(alpha)) * cos(radians(beta)),10*sin(radians(beta)),lookat_current[0],lookat_current[1],0,0,-1.0,0)
#				else:
#					gluLookAt(lookat_current[0] ,lookat_current[1] ,30,lookat_current[0],lookat_current[1],0,0,1,0)
			gluLookAt(lookat_current[0] ,lookat_current[1] ,50,lookat_current[0],lookat_current[1],0,0,1,0)


			glMatrixMode(GL_MODELVIEW)
			glLoadIdentity()
			t=1*fabs(cos(radians(rot*5)))
			anim = t
			glPolygonMode(GL_FRONT_AND_BACK,GL_FILL)
			glShadeModel (GL_SMOOTH)
			glEnable (GL_CULL_FACE)
			glEnable (GL_LINE_SMOOTH)
			glEnable (GL_POLYGON_SMOOTH)
			glHint (GL_LINE_SMOOTH_HINT, GL_NICEST)

			glLoadIdentity()
			glLineWidth(4) 
			glColor4f(1.0,0,0,0.5)
			glCallList(4)

			for i,l in enumerate(locations[0:current_location]):
				
				glEnable(GL_BLEND)

				if (i == current_location-1) :
					glLineWidth(4) 
					glLoadIdentity()
					glTranslatef(zoom * float(l['longitude']) , zoom * float(l['latitude']),0)
					glColor4f(1,1,0,0.7)
					glCallList(3)			

				glLoadIdentity()
				glTranslatef(zoom * float(l['longitude']) , zoom * float(l['latitude']), 0)
				glScalef(2,2,2)
				if (i == current_location-1):
					glRotatef(rot,0,0,1)
					glScalef(1+2*anim,1+2*anim,1+2*anim)
				glColor4f(1,0,0,0.7)
				glCallList(2)
#				if (i == len(locations)-1):
#					glRotatef(rot,0,0,1)
#					t=1*fabs(cos(radians(rot*5)))
#					anim = log(t+1)
#					glScalef(1+anim,1+anim,1+anim)
#					glCallList(1)

			glEnable(GL_BLEND)
			glLineWidth(4) 
			glLoadIdentity()
			glPolygonMode(GL_FRONT_AND_BACK,GL_LINE)
			glTranslatef(lookat_current[0] , lookat_current[1], 0)
			glRotatef(rot,0,0,1)
			glScalef(2,2,2)
			t=1*fabs(cos(radians(rot*5)))
			anim = t
			glScalef(1+anim,1+anim,1+anim)
			glColor4f(0,1,0,0.9)
			glCallList(1)

#
# Drawing Text
#
			glEnable(GL_BLEND)
			BeginTextView()
			glMatrixMode(GL_MODELVIEW)
			glLoadIdentity()
			t = app_texts['acquire']
			glRasterPos2i(0, 0)
			glDrawPixels(t[2][0], t[2][1], GL_RGBA, GL_UNSIGNED_BYTE, t[1])	
			t = app_texts['locations']
			glRasterPos2i(0, 30)
			glDrawPixels(t[2][0], t[2][1], GL_RGBA, GL_UNSIGNED_BYTE, t[1])	
			t = app_texts['status']
			glRasterPos2i(0, 60)
			glDrawPixels(t[2][0], t[2][1], GL_RGBA, GL_UNSIGNED_BYTE, t[1])	
			

			glFlush();
			pygame.display.flip()
			try:
				result = queue_locations.get(False,0.1)
				locations.extend(result)
				print "MOTHER > There are %d locations saved ... :)" % ( len(locations) )
				print "MOTHER > last location:\n" , pformat(locations[-1])
				#current_location = len(locations)-1
				no_data = 0
			except QEmpty:
				if not e_startup.is_set():
					p_gps_upd.start()
					e_startup.set()
				no_data += r_chrono
				pass

			chrono_tmp = chrono
			chrono = pygame.time.get_ticks()/1000.0

		print 'MOTHER : closing queue locations'
		queue_locations.close()
		print 'MOTHER : waiting end of queue'
		queue_locations.join_thread()
		print 'MOTHER : set stopped event'
		e_stopped.set()
		print 'MOTHER : waiting for GPSUPDATER to end'
		p_gps_upd.join()
		print 'MOTHER : quit PyGame'
		pygame.quit()
		
