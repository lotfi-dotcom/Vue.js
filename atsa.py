

import tkinter as tk
import threading
import queue
import time
import gui_20230105 as GUI
import pepperlfuchs_20230814 as DEVICE
import rfid_20230113 as TAG
import hydra_20230918 as HYDRA
import aip_20230915 as AIP
import opc_20231218 as OPC
import json

class Backend:
	def __init__(self, master):
		"""
		Start the GUI and the asynchronous threads.
		"""
		self.master = master
		self.nameQ = "Backend"

		# Create the queue
		self.qBackend = queue.Queue()
		self.qFrontend = queue.Queue()
		self.qPeppi = queue.Queue()
		self.qHYDRA = queue.Queue()
		# ~ self.qDB = queue.Queue()
		self.qAiP = queue.Queue()
		self.qOPC = queue.Queue()


		# Set up the GUI part
		self.gui = GUI.Frontend(master, self.qFrontend, self.qBackend)
		self.master.attributes(
			'-fullscreen',
			self.master.varFullScreen.get()
		)
		# self.master.bind()

		# Set up the RFID TAG part
		self.EPC = TAG.RFID()

		# Set up the thread to do asynchronous I/O
		# More can be made if necessary
		self.peppi = DEVICE.PepperlFuchs()
		self.running = 1

		# FSM state for "AutoStart"
		# -1 : waiting
		#  0 : no error
		# >0 : error with number
		self.fsmState = dict(
			step = -1,
			alarm = 0,
			waiting = None,
			machine = None,
			rfid = None,
			logic = None,
			QR = 0,
			database = 1,
			hydra = None,
			aip = None,
			opc = None,
			ui = None,
			retry = 5, # times
			count = 0,
			timeout = 10, # sec
			timer = 0,
			wait = 0.1, # sec
		)
		self.fsmStorage = dict(
			Terminal = dict(
				TNR = 0,
				Order = [],
				Maschine = [],
				Personal = [],
				Reasons = [],
				Queue = []
			),
			RFID = dict(
				old = 0,
				new = 0
			),
			# ~ RFID = "",
			# ~ RFID = "8863871426",
			# ~ RFID = "8858373874",
			part=dict(
				rfid = "",
				status = "",
				fault = "",
				inspection = "",
				anr = dict(
					past = "",
					future = ""
				),
				atk = "",
				desc = "",
				report = "",
				scrap = dict(
					number = "",
					text = ""
				)
			),
			USR = "",
			ANR = "",
			KNR = "",
			MNR = "",
			ATK = "",
			ATKrecipe = "",
			LoadedRecipe = "",
			recipes = [],
			relations = [],


		)
		self.body = dict(
			ressource = self.nameQ,
			status = "404",
			data = "",
			error = ""
		)

		self.tAiP = threading.Thread(
			target = AIP.Terminal,
			name = "AiP",
			args = (self.qAiP, self.qBackend),
			daemon = True)
		self.tAiP.start()

		self.tHYDRA = threading.Thread(
			target = HYDRA.REST,
			name = "HYDRA",
			args = (self.qHYDRA, self.qBackend),
			daemon = True)
		self.tHYDRA.start()

		self.tPeppi = threading.Thread(
			target = DEVICE.PepperlFuchs,
			name = "PepperlFuchs",
			args = (self.qPeppi, self.qBackend),
			daemon = True)
		self.tPeppi.start()

		self.tOPC = threading.Thread(
			target = OPC.OPC,
			name = "OPC",
			args = (self.qOPC, self.qBackend),
			daemon = True)
		self.tOPC.start()



		self.tAutoStart = threading.Thread(
		 target=self.fsmAutoStart3,
		 name="AutoStart",
		 args=(),
		 daemon=True)
		self.tAutoStart.start()

		# ~ # Call static ressources
		self.qAiP.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "getHost"
			}
		)
		
		# Try find TNR with given PATH informations in gui settings
		self.triggerGetAipSettings()

		# ~ # Find Peppi
		self.triggerGetFindRFID()

		

		# Start the periodic call in the GUI to check
		# if the queue contains anything
		self.periodicCall()

	def periodicCall(self):
		"""
		Check every 100 ms if there is something new in the queue.
		"""
		# ~ if (not self.tAutoStart.is_alive()
			# ~ and self.master.varAutoStart.get()):
			# ~ self.tAutoStart.start()

		self.processQueue()

		# Autoscroll log
		if self.master.varAutoScroll.get():
			self.master.textLog.see("end")

		# Master kill
		if not self.running:
			# This is the brutal stop of the system. You may want to do
			# some cleanup before actually shutting it down.
			import sys
			sys.exit(1)

		self.master.after(100, self.periodicCall)

	# Main loop
	def processQueue(self):
		"""
		Handle all the messages currently in the queue (if any).
		"""
		while self.qBackend.qsize():
			try:
				msg = self.qBackend.get(0)
				if not self.master.varAutoStart.get():
					pass
					print("[%s] %s" %(self.nameQ, msg))

				# --------------------------
				if msg["Thread"] == "Peppi":

					# -------------------------
					if msg["Status"] == "find":
						try:
							callback = self.eventGetFindRFID(msg["result"])
							print("Event callback find rfid: ",callback,type(callback))
							if isinstance(callback, UserWarning):
								raise UserWarning(callback)
							elif isinstance(callback, ResourceWarning):
								raise ResourceWarning(callback)
							elif isinstance(callback, Exception):
								raise ResourceWarning(callback)
							elif len(callback) > 0:
								self.master.btnStep1.configure(style="Success.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] RFID Gerät an %s gefunden\n" % (
										msg["Thread"], callback
									),
									"success"
								)
							else:
								raise ResourceWarning(callback)
						except UserWarning as e:
							self.master.btnStep1.configure(style="Active.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e)
							)
						except ResourceWarning as e:
							self.master.btnStep1.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						
						self.qBackend.task_done()
						
						
						#if msg["result"] == "":
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Suche RFID Gerät")
							#self.master.btnStep1.configure(style="Active.TButton")
							#self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Suche RFID Gerät"))
							#self.fsmState["rfid"] = 0
						#elif msg["result"] == None:
							#pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnStep2.configure(text="RFID erfassen")
							#self.master.btnStep1.configure(style="Error.TButton")
							#self.master.textLog.insert(tk.END,
								#"[%s] %s\n" % (msg["Thread"], "Kein RFID Gerät gefunden"),
								#"error"
							#)
							#self.fsmState["rfid"] = None
							# ~ print("Set fsm RFID = 0")
						#else:
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							#self.master.btnStep1.configure(style="Success.TButton")
							#self.master.textLog.insert(tk.END, "[%s] RFID Gerät an %s gefunden\n" % (msg["Thread"], msg["result"]))
							#self.fsmState["rfid"] = 1
							# ~ print("Set fsm RFID = 1")

					elif msg["Status"] == "read":
						try:
							callback = self.eventReadRFID(msg["result"])
							print("Event callback rfid: ", callback,type(callback))
							if isinstance(callback, UserWarning):
								raise UserWarning(callback)
							elif isinstance(callback, ResourceWarning):
								if callback == ResourceWarning("keine RFID gefunden"):
									pass
								else:
									raise ResourceWarning(callback)
							elif isinstance(callback, Exception):
								raise ResourceWarning(callback)
							elif len(callback) > 0:
								self.master.btnStep1.configure(style="Success.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] %s gelesen\n" % (msg["Thread"], callback)
								)
							else:
								raise ResourceWarning(callback)
						except UserWarning as e:
							self.master.btnStep1.configure(style="Active.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e)
							)
						except ResourceWarning as e:
							self.master.btnStep1.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						
						self.qBackend.task_done()
					
					# ---------------------------
					#elif msg["Status"] == "read":
						#if msg["result"] == "":
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Lese RFID")
							#self.master.btnStep1.configure(style="Active.TButton")
						#elif msg["result"] == "error":
							# ~ self.master.varRFID.set("Keine RFID gefunden")
							#self.master.btnStep1.configure(style="Error.TButton")
							#self.master.textLog.insert(tk.END, "[%s] %s - Fehler beim RFID lesen\n" % (msg["Thread"], msg["result"]))
							#self.fsmState["rfid"] = 2
							# ~ print("Set fsm RFID = 2")
						#else:
							# ~ self.master.varRFID.set("%s" %self.eventReadRFID(msg["result"]))
							# ~ self.master.btnStep2.configure(style="Success.TButton")
							#self.master.textLog.insert(tk.END, "[%s] %s gelesen\n" % (msg["Thread"], self.eventReadRFID(msg["result"])))
							# ~ self.fsmState["rfid"] = 3
							# ~ print("Lese RFID")

					# -------------------------------
					elif msg["Status"] == "writeEPC":
						if msg["result"] == "":
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Lese RFID")
							self.master.btnStep1.configure(style="Active.TButton")
						elif msg["result"] == "error":
							# ~ self.master.varRFID.set("Keine RFID gefunden")
							self.master.btnStep1.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END, "[%s] %s - Fehler beim RFID lesen\n" % (msg["Thread"], msg["result"]))
							self.fsmState["rfid"] = 2
							# ~ print("Set fsm RFID = 2")
						else:
							# ~ self.master.varRFID.set("%s" %self.eventReadRFID(msg["result"]))
							# ~ self.master.btnStep2.configure(style="Success.TButton")
							self.master.textLog.insert(tk.END, "[%s] %s gelesen\n" % (msg["Thread"], self.eventReadRFID(msg["result"])))
							# ~ self.fsmState["rfid"] = 3
							print("Schreibe RFID")

					else:
						print("Not handled")
						pass

				elif msg["Thread"] == "Frontend":
				# -------------------------------

					# Protocoll "exit" -> X pressed
					if msg["do"] == "exit":
						self.master.quit()
						self.qBackend.task_done()

					# Button RFID
					# --------------------------
					elif msg["do"] == "btnRFID":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (msg["Thread"], "Schalter RFID gedrückt")
						)

						try:
							callback = self.eventBtnRFID(msg)
							if callback == True:
								self.master.btnStep1.configure(style="Active.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep1.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Button "Hydra"
					# ---------------------------
					elif msg["do"] == "btnHYDRA":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (msg["Thread"], "Schalter HYDRA gedrückt")
						)

						try:
							callback = self.eventBtnHYDRA(msg)
							if callback == True:
								self.master.btnStep2.configure(style="Active.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep2.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Button "AiP"
					# -------------------------
					elif msg["do"] == "btnAIP":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (msg["Thread"], "Schalter AiP gedrückt")
						)

						try:
							callback = self.eventBtnAIP(msg)
							if callback == True:
								self.master.btnStep3.configure(style="Success.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep3.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Button "Report"
					# -------------------------
					elif msg["do"] == "btnReport":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (msg["Thread"], "Schalter Report gedrückt")
						)

						try:
							callback = self.eventBtnReport(msg["data"])
							if callback == True:
								self.master.btnStep3.configure(style="Success.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep3.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Button "Scrap"
					# -------------------------
					elif msg["do"] == "btnScrap":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (
								msg["Thread"], "Schalter Ausschuss gedrückt"
							)
						)

						try:
							callback = self.eventBtnScrap(msg["data"])
							if callback == True:
								self.master.btnStep3.configure(style="Active.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep3.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Button "NumPadOK"
					# -------------------------
					elif msg["do"] == "btnNumPadOK":
						self.master.textLog.insert(tk.END,
							"[%s] %s\n" % (
								msg["Thread"], "Schalter NumPad 'OK' gedrückt"
							)
						)

						try:
							callback = self.eventBtnNumPadOK()
							if callback == True:
								self.master.btnStep3.configure(style="Success.TButton")
							else:
								raise ValueError(callback)

						except Exception as e:
							self.master.btnStep3.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						self.qBackend.task_done()

					# Default
					else:
						pass

				# ----------------------------
				elif msg["Thread"] == "HYDRA":

					# ---------------------------------
					if  msg["Status"] == "getRFIDinfo":
						
						try:
							callback = self.eventGetRFIDinfo(msg["result"])
							
							if isinstance(callback, UserWarning):
								raise UserWarning(callback)
							elif isinstance(callback,ResourceWarning):
								raise ResourceWarning(callback)
							elif len(callback) > 0:
								self.master.btnStep1.configure(style="Success.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], callback)
								)
							else:
								raise ResourceWarning(callback)
						except UserWarning as e:
							self.master.btnStep1.configure(style="Active.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e)
							)
						except ResourceWarning as e:
							self.master.btnStep1.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						
						self.qBackend.task_done()
						
						
						
						# ~ if msg["result"] == "":
							# ~ self.master.textLog.insert(tk.END,
								# ~ "[%s] %s\n" % (
									# ~ msg["Thread"],
									# ~ "RFID wird abgefragt"
								# ~ )
							# ~ )
						# ~ else:
							# ~ try:
								# ~ callback = self.eventGetRFIDinfo(msg["result"])
								# ~ if isinstance(callback, Exception):
									# ~ raise ResourceWarning(callback)
								# ~ else:
									# ~ self.master.btnStep2.configure(
										# ~ style="Success.TButton"
									# ~ )
									# ~ self.master.textLog.insert(tk.END,
											# ~ "[%s] %s\n" % (
												# ~ msg["Thread"],
												# ~ callback
											# ~ )
										# ~ )
							# ~ except Exception as e:
								# ~ self.master.btnStep2.configure(style="Error.TButton")
								# ~ self.master.textLog.insert(
									# ~ tk.END,
									# ~ "[%s] %s\n" % (msg["Thread"], e),
									# ~ "error"
								# ~ )
							# Debug purpose only
							# ~ else:
								# ~ # Follow up event
								# ~ for item in self.fsmStorage["Terminal"]["Queue"]:
									# ~ if item["rfid"] == self.fsmStorage["part"]["rfid"]:
										# ~ self.triggerSetAGinterrupt()
										# ~ break
								# ~ else:
									# ~ self.triggerGetPPAchain()

						# ~ self.qBackend.task_done()

					# ---------------------------------
					if  msg["Status"] == "getPPAchain":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END,
								"[%s] %s\n" % (
									msg["Thread"],
									"Planauftrag wird abgerufen"
								)
							)
						else:
							try:
								callback = self.eventGetPPAchain(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									self.master.btnStep2.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(tk.END,
											"[%s] %s\n" % (
												msg["Thread"],
												callback
											)
										)
							except Exception as e:
								self.master.btnStep2.configure(style="Error.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)

						self.qBackend.task_done()

					# ---------------------------------
					if  msg["Status"] == "getTerminalInfo":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END,
								"[%s] %s\n" % (
									msg["Thread"],
									"Fehlergründe werden abgerufen"
								)
							)
						else:
							try:
								callback = self.eventGetTerminalInfo(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									self.master.btnStep2.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(tk.END,
											"[%s] %s\n" % (
												msg["Thread"],
												callback
											),
											"success"
										)
							except Exception as e:
								self.master.btnStep2.configure(style="Error.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)

						self.qBackend.task_done()

					# ------------------------------------
					if msg["Status"] == "getBySecondRFID":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END,
								"[%s] %s\n" % (msg["Thread"], "LosNr. wird abgefragt")
							)
							self.master.btnStep2.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							self.master.btnStep2.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
								"[%s] %s\n" % (msg["Thread"], "Server nicht erreichbar"),
								"error"
							)
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							try:
								if self.eventGetBySecondRFID(msg["result"]) == True:
									self.master.textLog.insert(tk.END,
										"[%s] LosNr. hat RFID = %s\n" % (
											msg["Thread"],
											self.fsmStorage["RFID"]["new"]
										)
									)
									self.master.btnStep2.configure(style="Success.TButton")
								else:
									raise ValueError(self.eventGetBySecondRFID(msg["result"]))

							except Exception as e:
								self.master.btnStep2.configure(style="Error.TButton")
								# ~ print(e)
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)
								pass
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
							# ~ self.eventGetMachineState(msg["result"])
						self.qBackend.task_done()

				# ---------------------------
				elif msg["Thread"] == "REST":
					# NOTE: fsmState for machine is
					# set in eventGetMachineState!
					# ------------------------------------
					if msg["Status"] == "getMachineState":
						if msg["result"] == "":
							# ~ self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Maschinenzustand wird abgefragt"))
							self.master.btnStep1.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							self.master.btnStep1.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							# ~ self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventGetMachineState(msg["result"])))
							# ~ self.master.btnStep1.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
							self.eventGetMachineState(msg["result"])
							pass

					# -----------------------------------
					if msg["Status"] == "ClampOrRelease":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Spannen wird ausgeführt"))
							self.master.btnStep3.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							self.master.btnStep3.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventClampOrRelease(msg["result"])))
							# ~ self.master.btnStep3.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

					# --------------------------
					if msg["Status"] == "Reset":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Spannen wird ausgeführt"))
							self.master.btnStep1.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							self.master.btnStep4.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventReset(msg["result"])))
							# ~ self.master.btnStep4.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

					# ------------------------------------
					if msg["Status"] == "StartInspection":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Messen wird ausgeführt"))
							self.master.btnStep5.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							self.master.btnStep5.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventStartInspection(msg["result"])))
							# ~ self.master.btnStep5.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

					# --------------------------------------
					if msg["Status"] == "getAllRecipeNames":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Rezepte werden abgerufen"))
							# ~ self.master.btnStep5.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							# ~ self.master.btnStep4.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s Rezept(e) geladen\n" % (msg["Thread"],msg["Status"], self.eventGetAllRecipeNames(msg["result"])))
							# ~ self.master.btnStep4.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
					# ----------------------------------
					if msg["Status"] == "getLastResult":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Ergebnis wird abgerufen"))
							self.master.btnStep6.configure(style="Active.TButton")
							pass
						elif msg["result"] == None:
							pass
						else:
							self.master.textLog.insert(tk.END, "[%s] %s - %s Ergebnis geladen\n" % (msg["Thread"],msg["Status"], self.eventGetLastResult(msg["result"])))

					# ----------------------------------
					if msg["Status"] == "getResultById":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Ergebnis wird abgerufen"))
							# ~ self.master.btnStep6.configure(style="Active.TButton")
							pass
						elif msg["result"] == None:
							pass
						else:
							self.master.textLog.insert(tk.END, "[%s] %s - %s Ergebnis geladen\n" % (msg["Thread"],msg["Status"], self.eventGetResultById(msg["result"])))

					# ---------------------------------------
					if msg["Status"] == "getPeriodResultIds":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Ergebnisse für Import werden abgerufen"))
							pass
						elif msg["result"] == None:
							pass
						else:
							self.master.textLog.insert(tk.END, "[%s] %s - Ergebnisse geladen (%s) \n" % (msg["Thread"],msg["Status"], self.eventDatabaseImport(msg["result"])))

					# -------------------------------
					if msg["Status"] == "LoadRecipe":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Rezept wird ausgewählt"))
							self.master.btnStep4.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							# ~ self.master.btnStep4.configure(style="Error.TButton")
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - Rezept geladen (%s) \n" % (msg["Thread"],msg["Status"], self.eventLoadRecipe(msg["result"])))
							# ~ self.master.btnStep4.configure(style="Success.TButton")
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

				# --------------------------
				elif msg["Thread"] == "OPC":

					# -----------------------------------
					if msg["Status"] == "write":
						try:
							callback = self.eventSetOPC(msg["result"])
							print("Event callback OPC: ", callback,type(callback))
							if isinstance(callback, UserWarning):
								raise UserWarning(callback)
							elif isinstance(callback,ResourceWarning):
								raise ResourceWarning(callback)
							elif len(callback) > 0:
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], callback)
								)
							else:
								raise ResourceWarning(callback)
						except UserWarning as e:
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e)
							)
						except ResourceWarning as e:
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
					
					self.qBackend.task_done()
						
						# ~ if msg["result"] == "":
							# ~ self.master.textLog.insert(
								# ~ tk.END,
								# ~ "[%s] %s\n" % (msg["Thread"], "OPC wird gesendet")
							# ~ )

						# ~ elif msg["result"] == None:
							# ~ raise UserWarning(
								# ~ "%s:%s" % (msg["Thread"], msg["Status"])
							# ~ )

						# ~ else:
							# ~ self.master.textLog.insert(
								# ~ tk.END,
								# ~ "[%s] %s\n" % (
									# ~ msg["Thread"],
									# ~ "Host = %s" % self.eventSetOPC(msg["result"])
								# ~ ),
								# ~ None if msg["result"]["status"] == 200 else "warning"
							# ~ )

						# ~ self.qBackend.task_done()

				# --------------------------
				elif msg["Thread"] == "AiP":

					# -----------------------------------
					if msg["Status"] == "getHost":
						if msg["result"] == "":
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (msg["Thread"], "Host wird ermittelt")
							)

						elif msg["result"] == None:
							raise UserWarning(
								"%s:%s" % (msg["Thread"], msg["Status"])
							)

						else:
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (
									msg["Thread"],
									"Host = %s" % self.eventGetHost(msg["result"])
								),
								None if msg["result"]["status"] == 200 else "warning"
							)

						self.qBackend.task_done()
						
					# -----------------------------------
					if msg["Status"] == "getAipSettings":
						try:
							callback = self.eventGetAipSettings(msg["result"])
							if isinstance(callback, UserWarning):
								raise UserWarning(callback)
							elif isinstance(callback,ResourceWarning):
								raise ResourceWarning(callback)
							elif callback:
								self.master.btnStep3.configure(style="Success.TButton")
								self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], callback),
									"success"
								)
								# TNR is known -> # Call Scrap Reasons
								self.triggerGetTerminalInfo()
							else:
								raise ResourceWarning(callback)	
						except UserWarning as e:
							self.master.btnStep3.configure(style="Active.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e)
							)
						except ResourceWarning as e:
							self.master.btnStep3.configure(style="Error.TButton")
							self.master.textLog.insert(tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
							)
						
						self.qBackend.task_done()
						
						# ~ if msg["result"] == "":
							# ~ self.master.textLog.insert(
								# ~ tk.END,
								# ~ "[%s] %s\n" % (msg["Thread"], "AiP Einstellungen ermitteln")
							# ~ )

						# ~ elif msg["result"] == None:
							# ~ raise UserWarning(
								# ~ "%s:%s" % (msg["Thread"], msg["Status"])
							# ~ )

						# ~ else:
							# ~ self.master.textLog.insert(
								# ~ tk.END,
								# ~ "[%s] %s\n" % (
									# ~ msg["Thread"],
									# ~ "%s" % self.eventGetAipSettings(msg["result"])
								# ~ ),
								# ~ None if msg["result"]["status"] == 200 else "warning"
							# ~ )

						# ~ self.qBackend.task_done()

					# -----------------------------------
					if msg["Status"] == "getOrderList":
						if msg["result"] == "":
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (msg["Thread"],"Lokale Aufträge abrufen")
							)
						else:
							try:
								callback = self.eventGetOrderList(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									self.master.btnStep3.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(
										tk.END,
										"[%s] %s\n" % (msg["Thread"],callback)
									)
							except Exception as e:
								self.master.btnStep3.configure(style="Error.TButton")
								self.master.textLog.insert(
									tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)
							# Only for debug purpose
							# ~ else:
								# Follow up event

								# ~ self.triggerSetAGregister()

						self.qBackend.task_done()

					# -----------------------------------
					if msg["Status"] == "setAGregister":
						if msg["result"] == "":
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (msg["Thread"],"Auftrag anmelden")
							)
						else:
							try:
								callback = self.eventSetAGregister(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									print("Callback: ",callback)
									self.master.btnStep3.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(
										tk.END,
										"[%s] %s\n" % (msg["Thread"],callback)
									)
							except Exception as e:
								self.master.btnStep3.configure(style="Error.TButton")
								self.master.textLog.insert(
									tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)

						self.qBackend.task_done()

					# -----------------------------------
					if msg["Status"] == "setAGinterrupt":
						if msg["result"] == "":
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (msg["Thread"],"Auftrag abmelden")
							)
						else:
							try:
								callback = self.eventSetAGinterrupt(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									self.master.btnStep3.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(
										tk.END,
										"[%s] %s\n" % (msg["Thread"],callback)
									)
							except Exception as e:
								self.master.btnStep3.configure(style="Error.TButton")
								self.master.textLog.insert(
									tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)

						self.qBackend.task_done()

					# -----------------------------------
					if msg["Status"] == "setBooking":
						if msg["result"] == "":
							self.master.textLog.insert(
								tk.END,
								"[%s] %s\n" % (msg["Thread"],"Buchung absenden")
							)
						else:
							try:
								callback = self.eventSetReport(msg["result"])
								if isinstance(callback, Exception):
									raise ResourceWarning(callback)
								else:
									self.master.btnStep3.configure(
										style="Success.TButton"
									)
									self.master.textLog.insert(
										tk.END,
										"[%s] %s\n" % (msg["Thread"],callback,),
										"success"
									)
							except Exception as e:
								self.master.btnStep3.configure(style="Error.TButton")
								self.master.textLog.insert(
									tk.END,
									"[%s] %s\n" % (msg["Thread"], e),
									"error"
								)

						self.qBackend.task_done()


					# -----------------------------------
					if msg["Status"] == "bookingRequest":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Auftrag wird abgerufen"))
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventBookingRequest(msg["result"])))
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

					# ----------------------------------------
					if msg["Status"] == "bookingConfirmation":
						if msg["result"] == "":
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], "Auftrag wird gebucht"))
							self.master.btnStep7.configure(style="Active.TButton")
							pass
							# ~ dir(self.master)
							# ~ self.master.varRFID.set("Maschinenzustand wird abgefragt")
							# ~ self.master.btnReadRFID.configure(text="Bitte warten")
						elif msg["result"] == None:
							pass
							# ~ self.master.varRFID.set("Kein RFID Gerät gefunden")
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")
						else:
							# ~ callback = self.eventGetMachineState(msg["result"])
							self.master.textLog.insert(tk.END, "[%s] %s - %s\n" % (msg["Thread"],msg["Status"], self.eventBookingConfirmation(msg["result"])))
							# ~ self.master.varRFID.set("RFID Gerät an %s" %msg["result"])
							# ~ self.master.btnReadRFID.configure(text="RFID erfassen")

					# Default
					else:
						pass

				# Default
				else:
					print("[Backend] Error in Backend queue with: %s" %msg)

				# Check contents of message and do what it says
				# As a test, we simply print it
				# ~ msg.widget.configure(text="Bitte warten")
				# ~ print ("[Backend] %s %s" %(msg.widget.cget("text"),type(msg.widget)))
			except Exception as e:
				self.master.textLog.insert(
					tk.END,
					"[%s] %s: %s\n" % (self.nameQ, e.__class__.__name__, e),
					"error"
				)
				# ~ print(e.__class__.__name__,e)
				pass

	def fsmAutoStart3(self):
		print("[%s] Thread FSM Autostart started" %self.nameQ)
		while self.running:
			try:
				while self.master.varAutoStart.get():

					# Handbrake
					time.sleep(self.fsmState["wait"])
					print(self.fsmState)

					# Step -1: Clean up
					# -----------------
					if self.fsmState["step"] == -1:
						self.fsmCleanUp3()

					# Step -2: RFID manuell
					# ---------------------
					elif self.fsmState["step"] == -2:
						# Check if any Toplevel windows are open
						children = [element.winfo_class() for element in self.master.winfo_children()]
						if not "Toplevel" in children:
							# Focus input
							self.master.entryRFID.focus_set()

						# Check for new QR input
						if self.fsmStorage["part"]["rfid"] == "":
							 # empty RFID
							continue

						else:
							# Input was made
							# add some logic?
							self.master.textLog.insert(tk.END,
								"[FSM %s] RFID %s manuell erfasst\n" % (
									self.fsmState["step"],
									self.fsmStorage["part"]["rfid"]
								),
								("info",)
							)
							# Clear
							self.fsmState["step"] = 0

							continue
					
					# Parking FSM for debugging
					elif self.fsmState["step"] == -3:
						continue
					
					# Step 0: UI (KNR)
					# ------------------------
					elif self.fsmState["step"] == 0:
						if self.master.varAiPKNR.get() == "":
							self.master.entryRFID.configure(style = "Active.TEntry")
							self.master.varRFID.set("Benutzer abfragen")
						
						# Request
						if self.fsmState["ui"] == None:
							# KNR not set
							if self.master.varAiPKNR.get() == "":
								self.gui.createWindowNumPad(
									config = {
										"title": "Benutzer KNR eingeben",
										"buttons": {
											"ok": "KNR bestätigen",
											"cancel": "CE"
										}
									}
								)
								self.fsmState["ui"] = -1
							# KNR is set
							else:
								self.fsmState["ui"] = 0
							
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["ui"] < 0 :
								continue

						elif self.fsmState["ui"] > 0 :
							# Restart KNR request
							self.master.entryRFID.configure(style="Error.TEntry")
							self.master.varRFID.set("Benutzer KNR ist leer")
							self.fsmState["ui"] = None
							# ~ self.fsmState["step"] = -1
							continue

						# Response success
						else:
							self.master.entryRFID.configure(style="Success.TEntry")
							self.master.varRFID.set("Benutzer gespeichert")
							self.fsmState["ui"] = None
							self.fsmState["step"] += 1
							continue

					# Step 1: RFID
					# ------------
					elif self.fsmState["step"] == 1:
						# Check permanetaly KNR login
						if self.master.varAiPKNR.get() == "":
							self.fsmState["step"] = 0
						
						self.master.entryRFID.configure(style="Active.TEntry")
						# ~ self.master.varRFID.set("RFID erfassen")

						# No device
						if self.fsmState["rfid"] == None:
							self.master.varRFID.set("RFID Gerät nicht gefunden")
							time.sleep(5)
							self.triggerGetFindRFID()
							# ~ self.fsmState["step"] = -1
							continue
						
						# Searching Device
						elif self.fsmState["rfid"] == 0:
							self.master.varRFID.set("RFID Gerät suchen")
							continue
						
						# Waiting
						elif self.fsmState["rfid"] < 0:
							self.master.varRFID.set("RFID erfassen")
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								# disable timeout for debug
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# RFID device ready but not read yet
						elif self.fsmState["rfid"] == 1:
							# comment for offline debug
							self.triggerGetRFID()
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Multiple / None RFID in antenna field
						elif self.fsmState["rfid"] == 2:
							time.sleep(1)
							self.triggerGetRFID()
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# valid RFID found
						elif self.fsmState["rfid"] > 4:
							self.master.varRFID.set("RFID gelesen")
							self.master.entryRFID.configure(style="Success.TEntry")
							self.fsmState["rfid"] = 1
							self.fsmState["step"] += 1
							continue

						# Default
						else:
							self.master.varRFID.set("RFID Fehler")
							self.master.entryRFID.configure(style="Error.TEntry")
							msg = "[FSM %s] Fehler beim RFID erfassen (%s)\n" % (
								self.fsmState["step"],
								self.fsmState["rfid"]
							)
							self.master.textLog.insert(tk.END, msg, "error")
							self.fsmState["step"] = -1
							continue

					# Step 2: HYDRA (RFID info)
					# ------------------------
					elif self.fsmState["step"] == 2:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Hydra abrufen")

						# Request
						if self.fsmState["hydra"] == None:
							self.triggerGetRFIDinfo()
							self.fsmState["hydra"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["hydra"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# Response error
						elif self.fsmState["hydra"] > 0:
							# RFID is blocked production -> Reset FSM
							self.master.varRFID.set("Hydra Fehler")
							self.master.entryRFID.configure(style="Error.TEntry")
							self.fsmState["step"] = -1
							continue

						# Response success
						else:
							# Check for En-/De-Queque
							print("Check Terminal Queue:", self.fsmStorage["Terminal"]["Queue"])
							for item in self.fsmStorage["Terminal"]["Queue"]:
								print("Current Part: ", self.fsmStorage["part"])
								if item["rfid"] == self.fsmStorage["part"]["rfid"] :
									# Start dequeue RFID
									print("Dequeue")
									# Overwrite found item in queue
									# to local current processing part
									self.fsmStorage["part"] = item
									self.fsmState["step"] = 6
									break
							else:
								# For loop was not broken
								print("Enqueue")
								self.fsmState["step"] += 1

							# Clear Hydra for next Step
							self.fsmState["hydra"] = None
							continue

					# Step 3: HYDRA (PPAchain)
					# ------------------------
					elif self.fsmState["step"] == 3:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Planauftrag abrufen")
						# Request
						if self.fsmState["hydra"] == None:
							print(self.fsmStorage["part"])
							if len(self.fsmStorage["part"]["anr"]["past"]) > 0:
								self.triggerGetPPAchain()
								self.fsmState["hydra"] = -1
								self.fsmState["count"] = 0
								self.fsmState["timer"] = 0
								
								print("Inhalt von self.fsmStorage['part']:", self.fsmStorage["part"])
								print("Inhalt von self.fsmStorage['part']['anr']['past']:", self.fsmStorage["part"]["anr"]["past"])

								continue
							else:
								self.master.varRFID.set("ANR für Planauftrag nicht gefunden")
								self.master.entryRFID.configure(style="Error.TEntry")
								self.fsmState["step"] = -1
								continue

						# Response waiting
						elif self.fsmState["hydra"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# Response error
						elif self.fsmState["hydra"] > 0:
							# No chanied PPA found -> Reset FSM
							self.master.varRFID.set("Planauftrag nicht gefunden")
							self.master.entryRFID.configure(style="Error.TEntry")
							self.fsmState["step"] = -1
							continue

						# Response success
						else:
							self.fsmState["step"] += 1
							continue

					# Step 4: AiP (Order list)
					# ------------------------
					elif self.fsmState["step"] == 4:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Auftragsliste abrufen")

						# Request
						if self.fsmState["aip"] == None:
							self.triggerGetOrderList()
							self.fsmState["aip"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["aip"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# Response error
						elif self.fsmState["aip"] > 0:
							# RFID is blocked production -> Reset FSM
							self.master.entryRFID.configure(style="Error.TEntry")
							self.master.varRFID.set("Fehler in Auftragsliste")
							self.fsmCleanUp3()
							continue

						# Response success
						else:
							# Clear FSM AiP for next Step
							self.fsmState["aip"] = None
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							self.fsmState["step"] += 1
							continue

					# Step 5: AiP (EnQueue)
					# ---------------------
					elif self.fsmState["step"] == 5:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Helmschale anmelden")
						# Request
						if self.fsmState["aip"] == None:
							self.triggerSetAGregister()
							# ToDo -> better place to trigger OPC?
							self.triggerSetOPC()
							self.fsmState["aip"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["aip"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# Response error
						elif self.fsmState["aip"] > 0:
							self.master.entryRFID.configure(style="Error.TEntry")
							self.master.varRFID.set("Fehler in der Warteschlange")
							self.fsmState["step"] = -1
							# ~ self.fsmCleanUp3()
							continue

						# Response success
						else:
							# Add RFID to Queue
							self.fsmStorage["Terminal"]["Queue"].append(
								self.fsmStorage["part"]
							)
							self.master.entryRFID.configure(style = "Success.TEntry")
							self.master.varRFID.set("Anmelden erfolgreich")
							# Clear FSM after Enqueue
							self.fsmState["aip"] = None
							self.fsmState["step"] = -1
							continue


					# Step 6: UI (Report)
					# ------------------------
					elif self.fsmState["step"] == 6:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Buchung vorbereiten")
						# Request
						if self.fsmState["ui"] == None:
							# Open window for article report
							self.gui.createWindowReport(
								part = self.fsmStorage["part"]
							)
							self.fsmState["ui"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["ui"] < 0 :
								continue

						elif self.fsmState["ui"] > 0 :
							self.master.entryRFID.configure(style="Error.TEntry")
							self.master.varRFID.set("Buchung abgebrochen")
							self.fsmState["step"] += 1
							continue


						# Response success
						else:
							self.master.entryRFID.configure(style="Success.TEntry")
							self.master.varRFID.set("Buchung erfolgreich")
							self.fsmState["ui"] = None
							self.fsmState["step"] += 1
							continue

					# Step 7: AiP (DeQueue)
					# ------------------------
					elif self.fsmState["step"] == 7:
						self.master.entryRFID.configure(style="Active.TEntry")
						self.master.varRFID.set("Helmschale abmelden")
						
						# Request
						if self.fsmState["aip"] == None:
							self.fsmStepDequeue()
						
						# Response waiting
						elif self.fsmState["aip"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								continue
							else:
								self.fsmState["step"] = -1
								continue

						# Response error
						elif self.fsmState["aip"] > 0:
							self.master.entryRFID.configure(style="Error.TEntry")
							self.master.varRFID.set("Fehler in der Warteschlange")
							self.fsmState["step"] = -1
							continue

						# Response success
						else:
							self.master.entryRFID.configure(style="Success.TEntry")
							self.master.varRFID.set("Abmelden erfolgreich")
							self.fsmState["step"] += 1
							continue

					# Step: Default
					# -------------
					else:
						print("Default")
						self.fsmState["step"] = -1
						# ~ self.fsmCleanUp3()


			except Exception as e:
				print("[FSM %s] %s" % (self.fsmState["step"],e))
				pass
			finally:
				time.sleep(0.5)



	def fsmAutoStart2(self):
		print("[%s] Thread FSM Autostart started" %self.nameQ)
		while self.running:
			try:
				while self.master.varAutoStart.get():

					# Handbrake
					time.sleep(self.fsmState["wait"])

					# Step -1: Clean up
					# -----------------
					if self.fsmState["step"] == -1:
						# ~ print("\n\nStep %s: Clean up\n"
							# ~ %(self.fsmState["step"],
							# ~ )
						# ~ )
						self.fsmCleanUp2()

					# Step 0: QR
					# ----------
					elif self.fsmState["step"] == 0:
						# ~ print("Step %s: QR = %s"
							# ~ %(self.fsmState["step"],
								# ~ self.fsmState["QR"]
							# ~ )
						# ~ )

						# Check if any Toplevel windows are open
						children = [element.winfo_class() for element in self.master.winfo_children()]
						if not "Toplevel" in children:
							# Focus input
							self.master.entryRFID.focus_set()

						# Check for new QR input
						if self.fsmStorage["QR"] == "":
							 # empty input
							continue

						else:
							# Input was made
							# add some logic?
							# ~ self.master.textLog.insert(tk.END,
								# ~ "[FSM %s] QR code gescannt\n" % self.fsmState["step"],
								# ~ ("info",)
							# ~ )
							self.fsmState["step"] += 1
							continue

					# Step 1: HYDRA
					# -------------
					elif self.fsmState["step"] == 1:
						self.master.entryRFID.configure(style="Active.TEntry")
						# ~ print("Step %s: HYDRA %s"
							# ~ %(self.fsmState["step"],
								# ~ self.fsmState["hydra"]
							# ~ )
						# ~ )

						# Request
						if self.fsmState["hydra"] == None:
							self.qHYDRA.put(
								{
									"Thread": self.nameQ,
									"Status": "request",
									"do": "getBySecondRFID",
									"data":
										{
											"QR": self.fsmStorage["QR"]
										}
								}
							)
							self.fsmState["hydra"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Response waiting
						elif self.fsmState["hydra"] < 0:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								# ~ print("Waiting for HYDRA ",self.fsmState["timer"])
								continue
							else:
								self.fsmState["step"] = -1
								# ~ print("Timeout -> Clean up")
								continue

						# Response error
						elif self.fsmState["hydra"] > 0:
							# ~ print("Error in Hydra", self.fsmStorage["RFID"], "\n", self.fsmStorage["part"])
							# RFID is blocked production -> Reset FSM
							self.master.entryRFID.configure(style="Error.TEntry")
							self.fsmCleanUp2()
							continue

						# Response success
						else:
							# Hydra DLLOS is valid
							# ~ print("Valid DLLOS\n",
								# ~ self.fsmStorage["RFID"],
								# ~ "\n", self.fsmStorage["part"]
							# ~ )
							self.fsmState["step"] += 1
							# ~ self.fsmState["step"] = -1
							continue

					# Step 2: RFID read
					# -----------------
					elif self.fsmState["step"] == 2:
						self.master.entryRFID.configure(style="Active.TEntry")
						# ~ print("Step %s: RFID read %s"
							# ~ %(self.fsmState["step"],
								# ~ self.fsmState["rfid"]
							# ~ )
						# ~ )

						# Searching RFID device
						if self.fsmState["rfid"] == -2:
							self.master.varRFID.set("Keine o. zu viele RFID")
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue
						
						# Waiting
						elif self.fsmState["rfid"] == -1:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								# ~ print("Waiting for RFID read",self.fsmState["timer"])
								continue
							else:
								self.fsmState["step"] = -1
								# ~ print("Timeout -> Clean up")
								continue

						# RFID not read yet
						elif self.fsmState["rfid"] == 1:
							self.triggerGetRFID()
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Multiple / None RFID in antenna field
						elif self.fsmState["rfid"] == 3:
							if self.fsmState["count"] < self.fsmState["retry"]:
								msg = "[FSM %s] Keine o. zu viele RFID (%s)\n" % (
									self.fsmState["step"],
									self.fsmState["rfid"]
								)
								self.master.textLog.insert(tk.END, msg, "warning")

								time.sleep(1)
								self.qPeppi.put(
									{
										"Thread": self.nameQ,
										"Status": "request",
										"do":"read"
									}
								)

								self.fsmState["rfid"] = -1
								self.fsmState["count"] += 1
								# ~ self.fsmState["count"] = 0
							else:
								self.master.entryRFID.configure(style="Warning.TEntry")
								self.master.varRFID.set("Keine o. zu viele RFID")
								# CleanUp after max retry
								self.fsmState["step"] = -1
								continue

						# valid empty RFID found
						# ~ elif self.fsmState["rfid"] == 4:
						# Revesion:
						# Overwrite any single found RFID? -> empty or not!
						elif self.fsmState["rfid"] > 3:
							self.fsmState["step"] += 1
							continue

						# Default
						else:
							self.master.varRFID.set("Fehler beim RFID erfassen")
							self.master.entryRFID.configure(style="Error.TEntry")
							msg = "[FSM %s] Fehler beim RFID erfassen (%s)\n" % (
								self.fsmState["step"],
								self.fsmState["rfid"]
							)
							self.master.textLog.insert(tk.END, msg, "error")

							self.fsmState["step"] = -1
							continue

					# Step 3: RFID copy
					# ----------------------------
					elif self.fsmState["step"] == 3:
						self.master.entryRFID.configure(style="Active.TEntry")
						# ~ print("FSM %s: RFID copy %s"
							# ~ %(self.fsmState["step"],
								# ~ self.fsmState["rfid"]
							# ~ )
						# ~ )

						# Waiting
						if self.fsmState["rfid"] == -1:
							if self.fsmState["timer"] < self.fsmState["timeout"]:
								self.fsmState["timer"] += self.fsmState["wait"]
								# ~ print("Waiting for RFID copy",self.fsmState["timer"])
								continue
							else:
								self.fsmState["step"] = -1
								# ~ print("Timeout -> Clean up")
								continue

						# No device
						if self.fsmState["rfid"] == None:
							# ~ print("Step%s: fsm rfid = None" %self.fsmState["step"])
							self.qPeppi.put(
								{
									"Thread": self.nameQ,
									"Status": "request",
									"do":"find"
								}
							)
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							continue

						# Multiple / None RFID in antenna field
						elif self.fsmState["rfid"] == 3:
							if self.fsmState["count"] < self.fsmState["retry"]:
								msg = "[FSM %s] Keine o. zu viele RFID (%s)\n" % (
									self.fsmState["step"],
									self.fsmState["rfid"]
								)
								self.master.textLog.insert(tk.END, msg, "warning")

								time.sleep(1)
								self.qPeppi.put(
									{
										"Thread": self.nameQ,
										"Status": "request",
										"do": "copyRFID",
										"data": {
											"RFID": {
												"old": self.fsmStorage["RFID"]["old"],
												"new": self.fsmStorage["RFID"]["new"]
											}
										},
									}
								)

								self.fsmState["rfid"] = -1
								self.fsmState["count"] += 1
							else:
								self.master.entryRFID.configure(style="Warning.TEntry")
								self.master.varRFID.set("Keine o. zu viele RFID")
								# CleanUp after max retry
								self.fsmState["step"] = -1
							continue

						# RFID is blank or not
						# Revision: overwrite any single given RFID? -> empty or not!
						elif (self.fsmState["rfid"] == 4 or
							self.fsmState["rfid"] == 5):
							print("Article valid?")
							# Article is valid?
							if (self.fsmStorage["part"]["status"] == "G" and
									self.fsmStorage["part"]["inspection"] == "F"):
								print("article is valid!")
								# Log if RFID was empty or not
								if self.fsmState["rfid"] == 5:
									self.master.entryRFID.configure(style="Warning.TEntry")
									self.master.varRFID.set("RFID wurde überschrieben")
									msg = "[FSM %s] RFID mit %s überschrieben\n" % (
										self.fsmState["step"],
										self.fsmStorage["RFID"]["new"],
									)
									self.master.textLog.insert(tk.END, msg, "warning")
								if self.fsmState["rfid"] == 4:
									self.master.entryRFID.configure(style="Success.TEntry")
									self.master.varRFID.set("RFID erfolgreich geschrieben")
									msg = "[FSM %s] RFID %s erfolgreich geschrieben\n" % (
										self.fsmState["step"],
										self.fsmStorage["RFID"]["new"],
									)
									self.master.textLog.insert(tk.END, msg, "success")

								# Overwrite RFID -> empty or not!
								self.qPeppi.put(
									{
										"Thread": self.nameQ,
										"Status": "request",
										"do": "copyRFID",
										"data": {
											"RFID": {
												"old": self.fsmStorage["RFID"]["old"],
												"new": self.fsmStorage["RFID"]["new"]
											}
										},
									}
								)

							self.fsmState["step"] += 1
							self.fsmState["rfid"] = -1
							self.fsmState["count"] = 0
							self.fsmState["timer"] = 0
							continue

						# Default
						else:
							# Clean up
							self.fsmState["step"] = -1
						continue

					# Step: Default
					# -------------
					else:
						self.fsmCleanUp2()
						pass


			except Exception as e:
				print("[FSM %s] %s" % (self.fsmState["step"],e))
				pass
			finally:
				time.sleep(0.1)


	def fsmAutoStart(self):
		# ~ outQ = outQueue
		print("[%s] Thread Autostart started" %self.nameQ)
		while self.running:
			try:
				while self.master.varAutoStart.get():

					# Request machine state every step
					# Wait for new machine state with -1
					self.fsmState["machine"] = -1
					self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"getMachineState"})

					# Wait for new machine state
					timeout = 50
					timeToWait = timeout
					while self.fsmState["machine"] == -1:
						# Handbrake
						if not self.master.varAutoStart.get():
							break
						# Waiting
						if timeToWait > 0:
								if timeToWait % 10 == 0:
									print("Waiting for machine state")
								timeToWait -= 1
								time.sleep(0.1)
								continue
						# Timeout
						else:
							# ~ print("Request machine state again")
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"getMachineState"})
							timeToWait = timeout
							continue

					# Wait for cleared alarm
					if self.fsmState["alarm"] > 0:
						# ~ print("\n\nDEBUG ALARM = %s" %self.fsmState["alarm"])
						if self.fsmState["alarm"] == 28:
							# 28 = Lichtvorhang
							if self.fsmState["step"] == 6:
								pass
							else:
								self.fsmCleanUp()
								continue
						else:
							# ~ print("ALARM -> Reset FSM",self.fsmState)
							self.master.textLog.insert(tk.END, "[%s] Error %s with reset\n" % (self.nameQ, self.fsmState["alarm"]))
							# ~ # Reset FSM
							self.fsmCleanUp()
							continue


					# FSM begin

					# Homeposition
					if self.fsmState["step"] == 0:
						print("\n\nStep%s: machine state %s\n" %(self.fsmState["step"], self.fsmState["machine"]))
						# Uninit
						if self.fsmState["machine"] == None:
							print("Step1: fsm machine = None")
							continue
						# No error
						if self.fsmState["machine"] > 1:
							# Reset count and continue FSM
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] += 1
							continue
						# Waiting
						elif self.fsmState["machine"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Machine is waiting waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								self.fsmState["count"] += 1
								# ~ time.sleep(1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue
						# Error or uninit
						elif self.fsmState["machine"] == 0:
							print("Step%s: Machine got error or is uninit ..." %self.fsmState["step"])
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"getMachineState"})

						elif self.fsmState["machine"] == 1:
							print("Step%s: Machine error ... try to reset" %self.fsmState["step"])
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"Reset"})
						# Default
						else:
							print("Step%s: Machine default should never been reached" %self.fsmState["step"])
							continue

					# Read RFID
					elif self.fsmState["step"] == 1:
						print("\n\nStep%s: RFID %s %s\n" %(self.fsmState["step"], self.fsmState["rfid"], type(self.fsmState["rfid"])))
						# Is RFID already waiting?
						if self.fsmState["rfid"] == self.fsmState["waiting"]:
							# Set to wait
							self.fsmState["rfid"] = -1
						# Uninit
						if self.fsmState["rfid"] == None:
							print("Step%s: fsm rfid = None" %self.fsmState["step"])
							self.qPeppi.put({"Thread":self.nameQ,"Status":"request","do":"read"})
							continue
						# No error
						elif self.fsmState["rfid"] > 4:
							# Reset count and continue FSM
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] += 1
							continue
						# Waiting
						elif self.fsmState["rfid"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: RFID is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								self.fsmState["count"] += 1
								# ~ time.sleep(1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.fsmState["waiting"] = -1
								self.fsmState["rfid"] = None
								# ~ self.master.varAutoStart.set(False)
								continue
						# Error
						# RFID not read yet
						elif self.fsmState["rfid"] == 1:
							if self.fsmState["waiting"] != 1:
								self.qPeppi.put({"Thread":"Backend","Status":"request","do":"read"})
								self.fsmState["waiting"] = 1
							continue
						# RFID not found / multiple
						elif self.fsmState["rfid"] == 3:
							if self.fsmState["waiting"] != 3:
								self.qPeppi.put({"Thread":"Backend","Status":"request","do":"read"})
								self.fsmState["waiting"] = 3
							continue
						# RFID not init
						elif self.fsmState["rfid"] == 4:
							if self.fsmState["waiting"] != 4:
								self.qPeppi.put({"Thread":"Backend","Status":"request","do":"writeEPC"})
								self.fsmState["waiting"] = 4
							continue
						# Default
						else:
							print("Step%s: RFID default should never been reached" %self.fsmState["step"])
							break

					# Clamp or release Helmet
					elif self.fsmState["step"] == 2:
						print("\n\nStep%s: Clamp or Release %s %s\n" %(self.fsmState["step"], self.fsmState["machine"], type(self.fsmState["machine"])))
						# Waiting for clamp or release
						if self.fsmState["machine"] == self.fsmState["waiting"]:
						# ~ if (self.fsmState["waiting"] == 4 and
							# ~ self.fsmState["machine"] != 4):
							self.fsmState["machine"] = -1
						# Uninit
						if self.fsmState["machine"] == type(None):
							print("Step%: Clamp or Release = None" %self.fsmState["step"])
						# No error
						if self.fsmState["machine"] > 3:
							# Reset count and continue FSM
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							# Without booking += 2?
							self.fsmState["step"] += 1 if self.master.varHydraEnable.get() else 2
							continue
						# Waiting
						elif self.fsmState["machine"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Clamp or release is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								self.fsmState["count"] += 1
								time.sleep(1)
								continue
							# Timeout
							else:
								time.sleep(1)
								# ~ print("Max retry reached -> UI ERROR!")
								# ~ self.fsmState["count"] = 0
								# ~ self.master.varAutoStart.set(False)
								continue
						# Error
						# ErrorAcknowledge
						elif self.fsmState["machine"] == 1:
							if self.fsmState["waiting"] != 1:
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"Reset"})
								self.fsmState["waiting"] = self.fsmState["machine"]
							continue
						# Clamp or release
						elif self.fsmState["machine"] == 2:
							if self.fsmState["waiting"] != 2:
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"ClampOrRelease"})
								self.fsmState["waiting"] = self.fsmState["machine"]
							continue
						# Error
						elif self.fsmState["machine"] == 3:
							if self.fsmState["waiting"] != 3:
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"Reset"})
								self.fsmState["waiting"] = self.fsmState["machine"]
							continue

						# Default
						else:
							print("Step%s: Spannen default should never been reached")
							continue

					# Check logic
					elif self.fsmState["step"] == 3:
						print("\n\nStep%s: Logic %s %s\n" %(self.fsmState["step"], self.fsmState["logic"], type(self.fsmState["logic"])))
						# Get logic error
						self.fsmState["logic"] = self.fsmLogic()
						# Is logic already waiting?
						if self.fsmState["logic"] == self.fsmState["waiting"]:
							# ~ print("Step%s: fsm logic[%s] is waiting...")
							# ~ print("Step%s: Logic[%s] = waiting[%s]" %self.fsmState["step"],self.fsmstate["logic"],self.fsmstate["waiting"])
							# Set to wait
							self.fsmState["logic"] = -1
						# Uninit
						if self.fsmState["logic"] == None:
							print("Step%s: Logic = None" %self.fsmState["step"])
							continue
						# No error
						elif self.fsmState["logic"] == 0:
							# All fine -> load recipe and continue FSM
							payload = dict(
								recipeFile = self.fsmStorage["ATKrecipe"]
							)
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"LoadRecipe","data":payload})
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] += 1
							continue
						# Waiting
						elif self.fsmState["logic"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Logic is waiting for %s [%s/%s]" %(self.fsmState["step"],self.fsmState["waiting"],self.fsmState["count"],self.fsmState["retry"]))
								# no timeout possible / usefull
								# ~ self.fsmState["count"] += 1
								# ~ time.sleep(0.1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue

						# Error
						elif self.fsmState["logic"] == 1:
							# Terminal error
							print("Step%s: resolve Error[%s]" %(self.fsmState["step"],self.fsmState["logic"]))
							self.fsmStorage["USR"] = self.master.varHYDRATnr.get()
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						# Hydra error
						elif self.fsmState["logic"] == 2:
							print("Step%s: resolve Error[%s]" %(self.fsmState["step"],self.fsmState["logic"]))
							self.qAiP.put({"Thread":self.nameQ,"Status":"request","do":"bookingRequest"})
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						# Recipes on 3DPS
						elif self.fsmState["logic"] == 3:
							print("Step%s: resolve Error[%s]" %(self.fsmState["step"],self.fsmState["logic"]))
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"getAllRecipeNames"})
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						# Recipe ATK relation
						elif self.fsmState["logic"] == 4:
							print("Step%s: resolve Error[%s]" %(self.fsmState["step"],self.fsmState["logic"]))
							self.qDB.put({"Thread":self.nameQ,"Status":"request","do":"getAllRecipeRelations"})
							# ~ self.qDB.put({"Thread":self.nameQ,"Status":"request","do":"getRecipeNameByATK","data":self.fsmStorage["ATK"]})
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						elif self.fsmState["logic"] == 5:
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (self.nameQ, "Keine Verknüpfung vorhanden"))
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						elif self.fsmState["logic"] == 6:
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (self.nameQ, "Artikel hat keine Verknüpfung"))
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						elif self.fsmState["logic"] == 7:
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (self.nameQ, "Verknüpftes Rezept nicht gefunden"))
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						elif self.fsmState["logic"] == 8:
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (self.nameQ, "RFID noch unbekannt"))
							self.fsmState["step"] = 1
							continue

						elif self.fsmState["logic"] == 9:
							if self.fsmState["waiting"] != 9:
								payload = dict(
									recipeFile = self.fsmStorage["ATKrecipe"]
								)
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"LoadRecipe","data":payload})
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (self.nameQ, "Verknüpftes Rezept wurde noch nicht geladen"))
							self.fsmState["waiting"] = self.fsmState["logic"]
							continue
						# Default
						else:
							print("\nStep%s: default should never been reached" %self.fsmState["step"])
							continue

					# Start measurement
					elif self.fsmState["step"] == 4:
						print("Step%s: start measurement %s %s" %(self.fsmState["step"], self.fsmState["machine"], type(self.fsmState["machine"])))
						# waiting for "start"
						if self.fsmState["machine"] == self.fsmState["waiting"]:
						# ~ if (self.fsmState["waiting"] == 4 and
							# ~ self.fsmState["machine"] != 4):
							self.fsmState["machine"] = -1
						# Uninit
						if self.fsmState["machine"] == None:
							print("Step%s: start measurement = None" %self.fsmState["step"])
							continue
						# No error
						elif self.fsmState["machine"] > 4:
							# Start measurement
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] += 1
							continue
						# Waiting
						elif self.fsmState["machine"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Start measurement is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								self.fsmState["count"] += 1
								# ~ time.sleep(1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue
						# Error
						# "start" is ready
						elif self.fsmState["machine"] == 4:
							if self.fsmState["waiting"] != 4:
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"StartInspection"})
								self.fsmState["waiting"] = self.fsmState["machine"]
							continue
						# "start" not possible yet
						elif self.fsmState["machine"] < 4:
							# Try again clamp or relase (step = 2)
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] = 2
							continue
						# Default
						else:
							print("\nStep%s: default should never been reached" %self.fsmState["step"])
							continue

					# Wait for measurement to be finished
					elif self.fsmState["step"] == 5:
						print("Step%s: Waiting for measurement %s %s" %(self.fsmState["step"], self.fsmState["machine"], type(self.fsmState["machine"])))

						# ToDo: find better wait condition
						if self.fsmState["machine"] == 5:
							self.fsmState["machine"] = -1

						# No error
						elif self.fsmState["machine"] == 2:
							# Machine finished
							self.fsmState["count"] = 0
							self.fsmState["waiting"] = -1
							self.fsmState["step"] += 1
							continue

						# Waiting
						elif self.fsmState["machine"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Measurement is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								# no timeout possible / usefull
								# ~ self.fsmState["count"] += 1
								# ~ time.sleep(0.1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue

						# Default
						else:
							print("\nStep%s: default should never been reached" %self.fsmState["step"])
							continue


					# Save measurement
					elif self.fsmState["step"] == 6:
						print("Step%s: save measurement %s %s" %(self.fsmState["step"], self.fsmState["database"], type(self.fsmState["database"])))

						# Uninit
						if self.fsmState["database"] == None:
							print("Step%s: save measurement database = None" %self.fsmState["step"])
							continue

						# No error
						elif (self.fsmState["database"] == 1):
							# Save measurement
							self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"getLastResult"})
							self.fsmState["count"] = 0
							self.fsmState["step"] += 1
							continue

						# Waiting
						elif self.fsmState["database"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Save measurement is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								# no timeout possible / usefull
								# ~ self.fsmState["count"] += 1
								# ~ time.sleep(1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue
						# Error
						elif self.fsmState["machine"] > 4:
							continue
						# Default
						else:
							print("\nStep%s: default should never been reached" %self.fsmState["step"])
							continue

					# Wait for removal and breaking "Lichtschranke"
					elif self.fsmState["step"] == 7:
						print("Step%s: Removal %s %s" %(self.fsmState["step"], self.fsmState["machine"], type(self.fsmState["machine"])))

						# Wait for removal (invinite wait)
						# ToDo: find better wait condition
						# No error
						if self.fsmState["machine"] > 1:
							self.fsmState["machine"] = -1
						# Waiting
						elif self.fsmState["machine"] < 0:
							# Check timeout
							if self.fsmState["count"] < self.fsmState["retry"]:
								print("Step%s: Removal is waiting [%s/%s]" %(self.fsmState["step"],self.fsmState["count"],self.fsmState["retry"]))
								# no timeout possible / usefull
								# ~ self.fsmState["count"] += 1
								# ~ time.sleep(1)
								continue
							# Timeout
							else:
								print("Step%s: Max retry reached -> UI ERROR!" %self.fsmState["step"])
								self.fsmState["count"] = 0
								self.master.varAutoStart.set(False)
								continue
						# Default
						else:
							print("\nStep%s: default should never been reached" %self.fsmState["step"])
							continue

					# CleanUp
					else:
						self.fsmCleanUp()

			except Exception as e:
				print(e)
			finally:
				time.sleep(0.1)

	def fsmCleanUp3(self):
		# Preset FSM
		time.sleep(3)
		# RFID state 1 = connected but idle
		if self.fsmState["rfid"] == None or self.fsmState["rfid"] == 0:
			self.fsmState["rfid"] = self.fsmState["rfid"]
		else:
			self.fsmState["rfid"] = 1
		# ~ self.fsmState["rfid"] = 1 if self.fsmState["rfid"] else None
		self.fsmState["hydra"] = None
		self.fsmState["aip"] = None
		self.fsmState["ui"] = None

		self.fsmState["step"] = 0
		self.fsmState["waiting"] = None
		self.fsmState["count"] = 0
		self.fsmState["retry"] = 5


		# Preset Storage
		self.fsmStorage["RFID"] = dict(
			old = 0,
			new = 0,
		)
		self.fsmStorage["part"] = dict(
			rfid = "",
			status = "",
			fault = "",
			inspection = "",
			anr = dict(
				past = "",
				future = ""
			),
			atk = "",
			desc = "",
			report = "",
			scrap = dict(
				number = "",
				text = ""
			)
		)

		# ~ # Preset buttons
		btnUi = [
			self.master.btnStep1,
			self.master.btnStep2,
			self.master.btnStep3,
		]
		for btn in btnUi:
			btn.configure(style = "TButton")

		# Preset entry
		self.master.entryRFID.configure(style = "TEntry")

		# Preset inputs
		self.master.varRFID.set("")

		# Preset text log with a new line
		self.master.textLog.insert(tk.END, "\n-------------\n", "info")


		# Close open UI windows
		# ~ self.gui.checkOpenWindow("AiP",True)

		# ~ print("clean up done")
		return

	def fsmCleanUp2(self):
		# Preset FSM
		time.sleep(3)

		self.fsmState["rfid"] = 1 # 1 = connected but idle
		self.fsmState["hydra"] = None

		self.fsmState["step"] = 0
		self.fsmState["waiting"] = -1
		self.fsmState["count"] = 0
		self.fsmState["retry"] = 5


		# Preset Hydra
		self.fsmStorage["RFID"]["old"] = ""
		self.fsmStorage["RFID"]["new"] = ""
		self.fsmStorage["QR"] = ""
		self.part=dict(
			status="F",
			fault="",
			inspection="",
		)

		# ~ # Preset buttons
		btnUi = [
			self.master.btnStep1,
			self.master.btnStep2,
			self.master.btnStep3,
		]
		for btn in btnUi:
			btn.configure(style="TButton")

		# Preset entry
		self.master.entryRFID.configure(style="TEntry")

		# Preset inputs
		self.master.varRFID.set("")

		# Preset text log with a new line
		self.master.textLog.insert(tk.END, "\n")


		# Close open UI windows
		# ~ self.gui.checkOpenWindow("AiP",True)

		# ~ print("clean up done")
		return

	def fsmCleanUp(self):
		# Preset FSM
		self.fsmState["machine"] = None
		self.fsmState["rfid"] = None
		self.fsmState["logic"] = None
		self.fsmState["logic"] = None
		self.fsmState["step"] = 0
		self.fsmState["waiting"] = -1
		self.fsmState["count"] = 0

		self.fsmStorage["ATKrecipe"] = ""
		self.fsmStorage["LoadedRecipe"] = ""

		# Preset Hydra
		self.fsmStorage["ANR"] = ""
		self.fsmStorage["KNR"] = ""
		self.fsmStorage["MNR"] = ""
		self.fsmStorage["ATK"] = ""
		self.fsmStorage["RFID"] = ""

		# Preset buttons
		btnUi = [
			# ~ self.master.btnStep1,
			self.master.btnStep2,
			self.master.btnStep3,
			self.master.btnStep4,
			self.master.btnStep5,
			self.master.btnStep6,
			self.master.btnStep7,
		]
		for btn in btnUi:
			btn.configure(style="TButton")

		# Close open UI windows
		self.gui.checkOpenWindow("AiP",True)
		return

	def fsmLogic(self):
		# ~ print("\n%s\n" %self.fsmStorage)
		self.master.btnStep4.configure(style="Error.TButton")
		# check Terminal information
		if self.fsmStorage["USR"] == "":
			return 1

		# check Hydra information
		if (self.fsmStorage["ANR"] == ""
			or self.fsmStorage["KNR"] == ""
			or self.fsmStorage["MNR"] == ""
			or self.fsmStorage["ATK"] == ""):
			return 2

		# any recipes to load?
		if self.fsmStorage["recipes"] == []:
			return 3

		# found any recipe relations
		if self.fsmStorage["relations"] == []:
			return 4

		# Check ATK recipe relation
		# ~ print("### DEBUG ###\n%s\n%s" %(self.fsmStorage["relations"],self.fsmStorage["recipes"]))
		for relation in self.fsmStorage["relations"]:
			# ~ print("DEBUG RECIPE RELATION:",relation,self.fsmStorage["ATK"])
			if relation["Part"] == self.fsmStorage["ATK"]:
				self.fsmStorage["ATKrecipe"] = relation["Recipe"]
				break
		else:
			return 5

		if self.fsmStorage["ATKrecipe"] == "":
			return 6

		# Check for loadable recipes
		for recipe in self.fsmStorage["recipes"]:
			# ~ print("DEBUG RECIPE LOAD:",self.fsmStorage["ATKrecipe"],recipe)
			if self.fsmStorage["ATKrecipe"] == recipe:
				# ~ print("DEBUG RECIPE %s FOUND AND IS NOW LOADING" %recipe)
				break
		else:
			return 7


		# Try to setup recipe
		# (Debug only)
		if not self.master.varAutoStart.get():
			payload = dict(
				recipeFile = self.fsmStorage["ATKrecipe"]
			)
			self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"LoadRecipe","data":payload})

		# check RFID (should never been reached)
		if self.fsmStorage["RFID"] == "":
			return 8

		if self.fsmStorage["LoadedRecipe"] == "":
			return 9

		# no errors
		self.master.btnStep4.configure(style="Success.TButton")
		return 0


	def eventExit2(self):
		self.qPeppi.put("close")


	def initRFID(self,queue):
		self.peppi.find()
		# ~ self.queue.put("RFID init start")
		# ~ self.peppi = DEVICE.PepperlFuchs()
		self.peppi.setMultiTag()
		self.peppi.setMemBank3()
		# ~ queue.put(self.peppi)

	# ~ def eventReadRFID(self):

		# ~ # Check if varFILE got something to read
		# ~ if self.master.varFILE.get():
			# ~ self.master.entryFILE.config(bg="white")
			# ~ self.master.entryFILE.config(fg="black")
		# ~ else:
			# ~ self.master.entryFILE.config(bg=self.gui.color["SHorange"])
			# ~ self.master.entryFILE.config(fg="white")

		# ~ if not self.master.varFILE.get():
			# ~ return False

		# ~ return True

	def eventReadRFID(self, payload):
		harrEPC = []
		barrEPC = bytearray()
		callback = ""

		# States for "read" RFID
		# ----------------------
		# 0 = no device found
		# 1 = Device found
		# 2 = error while reading
		# 3 = succesfully reading EPC
		# 4 = RFID not init yet
		# 5 = RFID init ok
		
		# ~ print("event payload RFID:", payload)
		try:
			self.master.btnStep1.configure(style="Warning.TButton")
			if payload == "":
				raise UserWarning("RFID wird abgefragt")
			elif len(payload) == 0:
				raise ResourceWarning("RFID Gerät nicht bereit")
			elif payload[0]["count"] == 0:
				raise ResourceWarning("keine RFID gefunden")
			elif payload[0]["count"] == 1:
				harrEPC = payload[0]["data"][0]['EPC']
			elif payload[0]["count"] > 1:
				# ~ print("[Error] eventRFID payload: ", payload)
				raise ResourceWarning("zu viele RFID")
			else:
				pass
		except UserWarning as e:
			return e
		except Exception as e:
			# Set fsm sate -> retry
			self.fsmState["rfid"] = 2
			# ~ print("%s: %s" % (e.__class__.__name__,e))
			return e
			# ~ print(e)

		# Decode RFID
		try:
			# ~ print("harrEPC: ", harrEPC)
			
			barrRFID = bytearray.fromhex("".join(harrEPC))
			print("barrRFID: ", barrRFID)
			callback = str(self.EPC.decodeContent(barrRFID)["RFID"])
			print("callback: ", type(callback), callback)
			print("Part RFID: ", type(self.fsmStorage["part"]["rfid"]), self.fsmStorage["part"]["rfid"])
			#Store old RFID -> better use outside in a function!
			self.fsmStorage["RFID"]["old"] = callback
			self.fsmStorage["part"]["rfid"] = callback
			print("Save RFID: ", self.fsmStorage["part"]["rfid"])
			# Check if RFID is init / valid
			if (len(callback) < 6 or len(callback) > 11):
				self.fsmState["rfid"] = 4
				raise ResourceWarning("Nicht initialisierte RFID")
			else:
				self.fsmState["rfid"] = 5
				self.master.btnStep1.configure(style="Success.TButton")

		except Exception as e:
			self.master.btnStep1.configure(style="Error.TButton")
			# ~ print("%s: %s" % (e.__class__.__name__,e))
			return e
			# ~ print(e)
			# ~ return "Cant decode EPC"
		# ~ print("callback: ", callback,type(callback))
		return callback

	def eventGetMachineState(self, result):
		# Preset & Placeholder
		callback = []
		allowedInputs = []
		# ~ print("\n\nMaschineState\n%s\n" %result)
		# Strip result
		# ~ try:
		# Check HTTP status
		if result.get("status"):
			if result["status"] != 200:
				self.master.btnStep1.configure(style="Error.TButton")
				if result.get("error"):
					self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))
					return False


		# Check data
		if result.get("data"):
			# ~ print("#### DEBUG alarm:",self.fsmState["alarm"])
			# ~ print("\n\nDEBUG DATA VORHANDEN\n",result["data"])

			# Check for alarms
			if result["data"].get("ActiveAlarms"):
				# ~ print("\n\nDEBUG ACTIVEALARMS VORHANDEN\n")
				# Reset fsm alarm
				# ~ self.fsmState["alarm"] = 0
				for alarm in result["data"]["ActiveAlarms"]:
					# Save last alarm number
					self.fsmState["alarm"] = alarm["AlarmType"]
					# Collect all alarms
					callback.append(alarm["DefaultText"])
					# ~ print(alarm["DefaultText"])
			else:
				# ~ print("\n\nDEBUG ACTIVEALARMS NICHT VORHANDEN\n")
				self.fsmState["alarm"] = 0

			# Check allowed inputs
			if result["data"].get("UserInput.AllowedInputs"):
				allowedInputs = result["data"]["UserInput.AllowedInputs"].split(", ")
				# Confirmation requiered
				if "ErrorAcknowledge" in allowedInputs:
					self.fsmState["machine"] = 1
					print("Set fsm Machine = 1")
				# Valid state
				if "Klemmen" in allowedInputs:
					self.fsmState["machine"] = 2
					print("Set fsm Machine = 2")
				if "GrundstellungOderReset" in allowedInputs:
					self.fsmState["machine"] = 3
					print("Set fsm Machine = 3")
				if "Start" in allowedInputs:
					self.fsmState["machine"] = 4
					print("Set fsm Machine = 4")
				# Reset requiered
				if "GrundstellungOderReset" in allowedInputs and len(allowedInputs) == 1:
					self.fsmState["machine"] = 1
					print("Set fsm Machine = 1")

			# Check if squence is running
			if result["data"].get("InspectionSequence.CurrentState"):
				if result["data"]["InspectionSequence.CurrentState"] not in ["AwaitInput", "HomePosition"]:
					self.master.btnStep1.configure(style="Active.TButton")
					self.fsmState["machine"] = 5
					print("Set fsm Machine = 5")
				else:
					if len(callback) == 0:
						self.master.btnStep1.configure(style="Success.TButton")
					elif self.fsmState["machine"] == 1:
						self.master.btnStep1.configure(style="Error.TButton")
					else:
						self.master.btnStep1.configure(style="Warning.TButton")

			# Return machine state if no active alarms
			if len(callback) == 0:
				callback.append(allowedInputs)

		elif result.get("error"):
			self.master.btnStep1.configure(style="Error.TButton")

		else:
			print("DEBUG: cant find data")
		# ~ except Exception as e:
			# ~ return e
		# ~ print("#### DEBUG alarm:",self.fsmState["alarm"])
		return callback

	def eventClampOrRelease(self, result):
		# Preset & Placeholder
		callback = []
		allowedInputs = []
		print("\n\nClampOrRelease\n%s" %result)
		# Strip result
		try:
			# Check HTTP status
			if result.get("status"):
				# HTTP 200 = OK
				if result["status"] == 200:
					# Error found
					if result.get("error"):
						if result["error"] != "":
							if result["error"].get("title"):
								self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]["title"]))
								self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"Reset"})
							else:
								self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))

							# Button color
							self.master.btnStep3.configure(style="Error.TButton")
							return False
					# Data found
					if result.get("data"):
						if result["data"] == "OK":
							self.master.btnStep3.configure(style="Success.TButton")
							return True
					# getMachineState should fired first!
					# ToDo: watch autostart
					# ~ if self.fsmState["machine"] > 2:
						# ~ self.master.btnStep3.configure(style="Success.TButton")
						# ~ return True
					# Try Reset
					# ~ elif self.fsmState["machine"] == 1:
						# ~ self.master.btnStep3.configure(style="Error.TButton")
						# ~ self.qREST.put({"Thread":self.nameQ,"Status":"request","do":"Reset"})
						# ~ return False
					else:
						# no valid state reached yet
						self.master.btnStep3.configure(style="Warning.TButton")

				# HTTP 404 = Error
				else:
					self.master.btnStep3.configure(style="Error.TButton")
					self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))

		except Exception as e:
			return e

		return False

	def eventReset(self, result):
		# Preset & Placeholder
		callback = []
		allowedInputs = []
		print("\n\nReset\n%s" %result)
		# Strip result
		try:
			# Check HTTP status
			if result.get("status"):
				if result["status"] == 200:

					# Error found
					if result.get("error"):
						if result["error"].get("title"):
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]["title"]))
						else:
							self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))
						# Button color
						self.master.btnStep1.configure(style="Error.TButton")
						return False
					# No error
					else:
						self.master.btnStep1.configure(style="Success.TButton")
						self.master.btnStep4.configure(style="TButton")
					return True

				# HTTP 404 -> error
				else:
					self.master.btnStep1.configure(style="Error.TButton")
					self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))

		except Exception as e:
			return e

		return False

	def eventStartInspection(self, result):
		try:
			# Check HTTP status
			if result.get("status"):
				if result["status"] == 200:
					self.master.btnStep5.configure(style="Success.TButton")
					return True
				else:
					# HTTP 404 -> error
					self.master.btnStep5.configure(style="Warning.TButton")

			if result.get("error"):
				self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))
				self.master.btnStep5.configure(style="Error.TButton")

		except Exception as e:
			return e

		return False

	def eventBookingRequest(self, result):
		# ~ print("eventBookingRequest: %s" %result)
		if result.get("data"):
			# Do some plausibility before send?
			# Open UI from master and select order
			self.gui.createWindowAiP(result)
			return True
		return False

	def eventBookingConfirmation(self, result):
		# ~ print("eventBookingRequest: %s" %result)
		try:
			# Check HTTP status
			if result.get("status"):
				if result["status"] == 200:
					self.master.btnStep7.configure(style="Success.TButton")
					return True
				else:
					# HTTP 404 -> error
					self.master.btnStep7.configure(style="Warning.TButton")

			if result.get("error"):
				self.master.textLog.insert(tk.END, "[%s] %s\n" % (result["ressource"], result["error"]))
				self.master.btnStep7.configure(style="Error.TButton")

		except Exception as e:
			return e

		return False

	def eventSelectOrder(self, result):
		try:
			if result["status"] == 200:
				if result["data"].get("Orders"):
					# JSON
					ANR = result["data"]["Orders"][0]["ANR"]
					ATK = result["data"]["Orders"][0]["ATK"]
					# to fsm
					self.fsmStorage["ATK"] = ATK
					self.fsmStorage["ANR"] = ANR
				if result["data"].get("Persons"):
					# JSON
					KNR = result["data"]["Persons"][0]["KNR"]
					# to fsm
					self.fsmStorage["KNR"] = KNR
				if result["data"].get("MNR"):
					# JSON
					MNR = result["data"]["MNR"]["MNR"]
					# to fsm
					self.fsmStorage["MNR"] = MNR

				# ~ self.qDB.put({"Thread":self.nameQ,"Status":"request","do":"getRecipeNameByATK","data":self.fsmStorage["ATK"]})

		except Exception as e:
			print(e)

	def eventGetAllRecipeNames(self, result):
		# Do some plausibility before save?
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					self.fsmStorage["recipes"] = result["data"]
					return len(result["data"])
		return 0

	def eventGetAllRecipeRelations(self, result):
		# Do some plausibility before save?
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					self.fsmStorage["relations"] = result["data"]
					return len(result["data"])
		return 0

	def eventGetRecipeNameByATK(self, result):
		# Do some plausibility before save?
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					self.fsmStorage["ATKrecipe"] = result["data"]
					return True
			elif result["status"] == 404:
				print("[Error in %s] %s" %(result["ressource"],result["error"]))
			else:
				pass
		return False

	def eventGetLastResult(self, result):
		# Preset & Placeholder
		doc = dict(
			time = DB.storage.getUTC(None),
			hydra = dict(
				ANR = self.fsmStorage["ANR"],
				KNR = self.fsmStorage["KNR"],
				MNR = self.fsmStorage["MNR"],
				ATK = self.fsmStorage["ATK"],
				USR = self.fsmStorage["USR"],
			),
			rfid = self.fsmStorage["RFID"],
			result = None,
			measurement = None
		)

		# Do some plausibility before save?
		print("\n\nMAIN\n",result)
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					# Check for special results
					if result["data"].get("IsOkay"):
						# result status is a must have
						doc["result"] = result["data"]["IsOkay"]
						doc["measurement"] = result["data"]
						# Request insert in DB
						self.qDB.put({"Thread":self.nameQ,"Status":"request","do":"SaveInspection", "data":doc})
						# Request Hydra booking (if enabled)
						if self.master.varHydraEnable.get():
							self.qAiP.put({"Thread":self.nameQ,"Status":"request","do":"bookingConfirmation","data":doc})
						return True
			elif result["status"] == 404:
				print("[Error in %s] %s" %(result["ressource"],result["error"]))
			else:
				pass
		return False

	def eventDatabaseImport(self, result):
		# Preset & Placeholder
		# ~ print("DEBUG: \n\n",result)
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					self.DBimport["IDs"] = result["data"]
					self.DBimport["run"] = False
					return len(result["data"])


	def eventGetResultById(self, result):
		# Preset & Placeholder
		# ~ print("DEBUG: \n\n",result)
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):

					# UTC time format
					year = int(result["data"]["Timestamp"].split(" ")[0].split(".")[2])
					month = int(result["data"]["Timestamp"].split(" ")[0].split(".")[1])
					day = int(result["data"]["Timestamp"].split(" ")[0].split(".")[0])
					hour = int(result["data"]["Timestamp"].split(" ")[1].split(":")[0])
					minute = int(result["data"]["Timestamp"].split(" ")[1].split(":")[1])
					second = int(result["data"]["Timestamp"].split(" ")[1].split(":")[2])

					utc = "%04d-%02d-%02dT%02d:%02d:%02d+01:00" %(
						year,month,day,
						hour,minute,second
					)

					# Fill document for DB import
					doc = dict(
						time = utc,
						hydra = dict(
							ANR = "",
							KNR = "",
							MNR = "",
							ATK = "",
							USR = "",
						),
						rfid = "import",
						result = None,
						measurement = None
					)
					doc["result"] = result["data"]["IsOkay"]
					doc["measurement"] = result["data"]

					# ~ print(doc)
					# Request insert in DB
					self.qDB.put({"Thread":self.nameQ,"Status":"request","do":"ImportInspection", "data":doc})

		return True

	def eventGetHost(self, result):
		try:
			if result["status"] == 404:
				return ResourceWarning(result["error"])
		except Exception as e:
			return e
		else:
			self.master.varAiPHost.set(result["data"])
			return result["data"]

	def triggerGetOrderList(self):
		# Queue AiP for available booking options
		try:
			self.qAiP.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do": "getOrderList",
					"data": {
						"mnr": self.master.varAiPMNR.get(),
						"tnr": self.master.varAiPTNR.get(),
						"path": self.master.varAiPPath.get(),
					}
				}
			)
			return True

		except Exception as e:
			return e

	def triggerGetRFID(self):
		
		try:
			self.qPeppi.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do":"read"
				}
			)

		except Exception as e:
			return e
			
	def triggerGetFindRFID(self):
		try:
			self.qPeppi.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do":"find"
				}
			)
		except Exception as e:
			return e
			
	def eventGetFindRFID(self, result):
		print("FindRFID Device: ", type(result), result)
		try:
			if result == "":
				self.fsmState["rfid"] = 0
				raise UserWarning("RFID Gerät wird gesucht")
			elif result == None:
				self.fsmState["rfid"] = None
				raise ResourceWarning("Kein Port verfügbar")
			elif len(result) > 1:
				self.fsmState["rfid"] = 1
				return result
			else:
				pass
		except Exception as e:
			return e
			
	def triggerGetRFIDinfo(self):

		try:
			if len(self.fsmStorage["part"]["rfid"]) > 0:
				self.qHYDRA.put(
					{
						"Thread": self.nameQ,
						"Status": "request",
						"do": "getRFIDinfo",
						"data":
							{
								"rfid": self.fsmStorage["part"]["rfid"]
							}
					}
				)
			else:
				raise ValueError("RFID ist leer")

			return True

		except Exception as e:
			return e

	def eventGetOrderList(self, result):
		# Preset & Placeholder
		# ~ self.fsmState["aip"] = 1
		print(result)
		try:
			if result["status"] == 404:
				return ResourceWarning(result["error"])
			else:
				# Aip fetch successfully complete
				self.fsmStorage["Terminal"]["Order"] = result["data"]
				callback = "%s Aufträge geladen" % len(result["data"])
				# FSM state
				self.fsmState["aip"] = 0
				return callback
		except Exception as e:
			return e

	def eventSaveInspection(self, result):
		# Do some plausibility before save?
		# Debug only
		print("\n\nSAVEINSPECTION\n",result)
		if self.master.varFILEenable.get():
			self.save2file(self.readFile())

		if result.get("status"):
			if result["status"] == 200:
				self.master.btnStep6.configure(style="Success.TButton")

				return True
			elif result["status"] == 404:
				self.master.btnStep6.configure(style="Warning.TButton")
				print("[Error in %s] %s" %(result["ressource"],result["error"]))
			else:
				print(result)
				pass
		return False

	def eventImportInspection(self, result):
		# Do some plausibility before save?
		# Debug only
		# ~ print("\n\nSAVEINSPECTION\n",result)
		# ~ if self.master.varFILEenable.get():
			# ~ self.save2file(self.readFile())

		if result.get("status"):
			if result["status"] == 200:
				self.master.btnStep6.configure(style="Success.TButton")
				# Flag to get the next import job done
				self.DBimport["run"] = False
				return True
			elif result["status"] == 404:
				self.master.btnStep6.configure(style="Warning.TButton")
				print("[Error in %s] %s" %(result["ressource"],result["error"]))
			else:
				print(result)
				pass

		# Flag to get the next import job done
		self.DBimport["run"] = False
		return False

	def eventLoadRecipe(self, result):
		# Do some plausibility before save?
		# Debug only
		print("\n\nLOADRECIPE\n",result)
		if result.get("status"):
			if result["status"] == 200:
				if result.get("data"):
					if result["data"].get("Name"):
						self.master.btnStep4.configure(style="Success.TButton")
						self.fsmStorage["LoadedRecipe"] = result["data"]["Name"]
						return True
					else:
						return False
				if result.get("error"):
					if result["error"].get("detail"):
						self.master.btnStep4.configure(style="Error.TButton")
						self.master.textLog.insert(tk.END, "[%s] %s\n" % (msg["Thread"], result["error"]["detail"]))
					return False
			elif result["status"] == 404:
				self.master.btnStep4.configure(style="Error.TButton")
				print("[Error in %s] %s" %(result["ressource"],result["error"]))
			else:
				print(result)
				pass
		return False

	def eventBtnQR (self, result):

		try:
			if len(result["data"]["QR"]) > 0:
				self.fsmStorage["QR"] = result["data"]["QR"]
				# store RFID to verify later
				# ~ self.qPeppi.put(
					# ~ {
						# ~ "Thread": self.nameQ,
						# ~ "Status": "request",
						# ~ "do": "read"
					# ~ }
				# ~ )
				return True
			else:
				raise ValueError("QR ist leer")
			return True

		except Exception as e:
			return e

	def eventBtnRFID (self, result):

		# Queue RFID reader with "read"
		try:
			# ~ self.fsmStorage["RFID"] = "8863871426"
			# ~ self.fsmStorage["RFID"] = "8858373874"
			# ~ self.fsmState["rfid"] = 4

			self.qPeppi.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do": "read"
				}
			)
			return True

		except Exception as e:
			return e

	def eventBtnHYDRA (self, result):
		try:
			# ~ self.triggerGetTerminalInfo()
			self.triggerGetRFIDinfo()
			return True
			# ~ else:
				# ~ raise ValueError("RFID ist leer")

		except Exception as e:
			return e

	def eventBtnAIP (self, result):
		# Queue AiP for available booking options
		try:
			self.triggerGetOrderList()
			self.triggerGetPPAchain()
			# ~ self.gui.createWindowReport()
			return True

		except Exception as e:
			return e

	def eventBtnReport (self, result):

		try:
			self.fsmStorage["part"]["report"] = result["report"]
			if result["report"] == "Bestanden":
				# Booking
				self.triggerSetReport()
				self.fsmState["ui"] = 0
			elif result["report"] == "Rücklauf":
				# Refusal
				raise UserWarning("Buchung wurde abgebrochen")
			elif result["report"] == "Ausschuss":
				# Wait for Scrap reasons
				self.triggerGetScrapReason()
			else:
				raise UserWarning("Artikel muss gebucht werden")

			return True

		except Exception as e:
			self.fsmState["ui"] = 1
			return e

	def eventBtnScrap (self, result):

		try:
			number = result["scrap"]["number"]
			text = result["scrap"]["text"]

			self.fsmStorage["part"]["scrap"]["number"] = number
			self.fsmStorage["part"]["scrap"]["text"] = text
		except Exception as e:
			return e

		else:
			self.triggerSetReport()
			self.fsmState["ui"] = 0
			return True

	def eventBtnNumPadOK (self):

		try:
			if self.master.varAiPKNR.get() == "":
				raise UserWarning("Benutzer KNR ist leer")
			else:
				self.fsmState["ui"] = 0
				return True
		except Exception as e:

			self.fsmState["ui"] = 1
			return e

	def eventGetRFIDinfo(self, result):
		# Preset & Placeholder
		callback = ""
		try:
			if result == "":
				raise UserWarning("Hydra wird abgefragt")
			elif len(result) == 0:
				self.fsmState["hydra"] = 1
				raise ResourceWarning("Hydra ist nicht bereit")
			elif result["status"] == 404:
				self.fsmState["hydra"] = 1
				raise ResourceWarning(result["error"])
			else:
				pass
			
			# Save article data		
			los = result["data"]["v_los_bestand"]
			# ~ print("DLLos:\n",los)
			
			# Check if article is already booked
			# Mashine name with Number
			MNR = self.master.varAiPMNR.get()
			# Mashine name without number -> match against last dll
			fragment = "".join([char for char in MNR if not char.isdigit()])
			if fragment in los["masch_nr"]:
				atk = los["artikel"]
				bez = los["artikel_bez"]
				date = los["prod_dat"]
				status = los["status"]
				klasse = los["klasse"]
				self.fsmState["hydra"] = 3
				raise ResourceWarning(
					"%s(%s) bereits am %s als %s(%s) gebucht"
					%(bez, atk, date, klasse, status)
				)
			# ~ self.fsmStorage["part"]["rfid"] = los["dllosnr"]
			
			# MNR was not found in last dll
			self.fsmStorage["part"]["inspection"] = los["klasse"]
			self.fsmStorage["part"]["fault"] = los["ausschussgrund"]
			self.fsmStorage["part"]["status"] = los["status"]
			self.fsmStorage["part"]["anr"]["past"] = los["attrib_str05"]
			self.fsmStorage["part"]["atk"] = los["artikel"]
			self.fsmStorage["part"]["desc"] = los["artikel_bez"]

			# Article is scrap
			if self.fsmStorage["part"]["inspection"] == "A":
				self.fsmState["hydra"] = 2
				raise ResourceWarning("Artikel ist Ausschuss (%s)"
					% self.fsmStorage["part"]["inspection"]
				)
			# Article is in blocked / release stock
			if self.fsmStorage["part"]["status"] != "F":
				self.fsmState["hydra"] = 0
				raise UserWarning("Artikel ist nicht Freigegeben (%s)"
					% self.fsmStorage["part"]["status"]
				)

			callback = "Artikelinformation:\n\t%s\n\t%s\n\t%s(%s)" % (
				self.fsmStorage["part"]["desc"],
				self.fsmStorage["part"]["anr"]["past"],
				self.fsmStorage["part"]["status"],
				self.fsmStorage["part"]["inspection"],
			)

			# Article is fine
			self.fsmState["hydra"] = 0
			return callback

		except Exception as e:
			return e

	def triggerGetPPAchain(self):
		if len(self.fsmStorage["part"]["anr"]["past"]):
			self.qHYDRA.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do": "getPPAchain",
					"data":
						{
							"ag": self.fsmStorage["part"]["anr"]["past"]
						}
				}
			)
		else:
			return False

		return True

	def eventGetPPAchain(self, result):
		# Preset & Placeholder
		print("PPA Chain:\nFSM old Storage: Part", self.fsmStorage["part"])
		try:
			if result["status"] == 404:
				return ResourceWarning(result["error"])

			PPA = result["data"]["answer_data"]["PPAs"]
			# Mashine name with Number
			MNR = self.master.varAiPMNR.get()
			# Mashine name without number -> match it
			fragment = "".join([char for char in MNR if not char.isdigit()])
			# Search MNR fragment in data to obtain
			# the corresponding ag number
            print("+++++++++++das ist die ag ++++++++++++++++", ag)
			for ag in PPA:
				if fragment in ag["masch_nr"]: 
					print(
						ag["ag"],
						ag["artikel_bez"],
						ag["ag_bez"],
						ag["masch_nr"],
						ag["artikel_bez"]
					)
					self.fsmStorage["part"]["anr"]["future"] = ag["ag"]
					# ANR is fine
					self.fsmState["hydra"] = 0
					print("FSM new Storage: Part", self.fsmStorage["part"])
					return  "Arbeitsgang %s gefunden" % ag["ag"]
				else:
					continue

			return ResourceWarning("Kein Planauftrag gefunden")
			
		except Exception as e:
			self.fsmState["hydra"] = 1
			return e

	def triggerSetAGregister(self):
		try:
			self.qAiP.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do": "setAGregister",
					"data":
						{
							"tnr": self.master.varAiPTNR.get(),
							"anr": self.fsmStorage["part"]["anr"]["future"],
							"mnr": self.master.varAiPMNR.get(),
							"knr": self.master.varAiPKNR.get()
						}
				}
			)
		except Exception as e:
			return e

	def eventSetAGregister(self, result):
		# Preset & Placeholder
		callback = ""
		print("Old Queue: ", self.fsmStorage["Terminal"]["Queue"])
		try:
			# Error handle
			if result["status"] == 404:
				# Try to get a error number in brackets
				# to avoid so exception events
				errorNumber = result["error"].split("[")[1].split("] ")[0]
				errorText = result["error"].split("[")[1].split("] ")[1]
				if errorNumber in ["70", "0"]:
					print("ignore",errorNumber)
					pass
				else:
					raise ResourceWarning(result["error"])

			# Enqueue RFID if possible
			Queue = self.fsmStorage["Terminal"]["Queue"]
			part = self.fsmStorage["part"]
			for item in Queue:
				if item == part:
					# Enqueue RFID already done
					callback = "Auftrag %s bereits angemeldet" % (
						self.fsmStorage["part"]["anr"]["future"]
					)
			else:
				Queue.append(part)

			# Save new Queue
			self.fsmStorage["Terminal"]["Queue"] = Queue

			callback = "Auftrag %s angemeldet" % (
				self.fsmStorage["part"]["anr"]["future"]
			)

			# Enqueue RFID success
			self.fsmState["aip"] = 0
			return callback

		except Exception as e:
			# Enqueue failed
			self.fsmState["aip"] = 1
			return e

	def triggerSetAGinterrupt(self):
		self.qAiP.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "setAGinterrupt",
				"data":
					{
						"tnr": self.master.varAiPTNR.get(),
						"anr": self.fsmStorage["part"]["anr"]["future"],
						"mnr": self.master.varAiPMNR.get(),
						"knr": self.master.varAiPKNR.get()
					}
			}
		)

	def eventSetAGinterrupt(self, result):
		# Preset & Placeholder
		
		# Error handle
		try:
			if result["status"] == 404:
				# Try to get a error number in brackets
				# to avoid warnings as exception events
				errorNumber = result["error"].split("[")[1].split("]")[0]
				if errorNumber == "70":
					pass
				else:
					return ResourceWarning(result["error"])

			# Dequeue success
			self.fsmState["aip"] = 0
			return  "Auftrag %s abgemeldet" % (
				self.fsmStorage["part"]["anr"]["future"]
			)

		except Exception as e:
			# Dequeue failed
			self.fsmState["aip"] = 1
			return e
			
	def fsmStepDequeue(self):

		oldQueue = self.fsmStorage["Terminal"]["Queue"]
		newQueue = []
		part = self.fsmStorage["part"]

		# Dequeue part and interrupt ANR if possible
		for item in oldQueue:
			if item["rfid"] == part["rfid"]:
				# ignore dequeued part
				continue
			else:
				# keep other queued parts
				newQueue.append(item)

		# Check for any following ANR left in Queue
		for item in newQueue:
			if item["anr"]["future"] == part["anr"]["future"]:
				# Following part found -> dont interrupt ANR
				self.fsmState["aip"] = 0
				break
		else:
			# Interrupt ANR
			self.triggerSetAGinterrupt()
			# Await AiP AG interrupt
			self.fsmState["aip"] = -1
			self.fsmState["count"] = 0
			self.fsmState["timer"] = 0

		# Save new Queue
		self.fsmStorage["Terminal"]["Queue"] = newQueue

	def triggerSetReport(self):
		try:
			self.qAiP.put(
				{
					"Thread": self.nameQ,
					"Status": "request",
					"do": "setBooking",
					"data":
						{
							"anr": self.fsmStorage["part"]["anr"]["future"],
							"mnr": self.master.varAiPMNR.get(),
							"atk": self.fsmStorage["part"]["atk"],
							"knr": self.master.varAiPKNR.get(),
							"rfid": self.fsmStorage["part"]["rfid"],
							"egr": self.fsmStorage["part"]["report"],
							"egg": self.fsmStorage["part"]["scrap"]["number"],
							"tnr": self.master.varAiPTNR.get()
						}
				}
			)
		except Exception as e:
			return e

	def eventSetReport(self, result):
		# Preset & Placeholder
		# Dequeue failed
		self.fsmState["ui"] = 1

		# Error handle
		try:
			if result["status"] == 404:
				# Try to get a error number in brackets
				# to avoid so exception events
				# ~ errorNumber = result["error"].split("[")[1].split("]")[0]
				# ~ if  not errorNumber == "70":
				return ResourceWarning(result["error"])
		except Exception as e:
			return e

		try:
			# Dequeue success
			self.fsmState["ui"] = 0
			return  "Buchung '%s' erfolgreich" % (
				self.fsmStorage["part"]["report"]
			)
		except Exception as e:
			return e

	def triggerGetScrapReason(self):
		mnr = self.master.varAiPMNR.get()
		reasons = self.fsmStorage["Terminal"]["Reasons"]
		# ~ print(reasons)
		# Create Window to select Scrap number / reason
		self.gui.createWindowSelectScrap(scrap = reasons)

	def triggerGetOPC(self):
		self.qOPC.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "read"
			}
		)

	def triggerSetOPC(self):
		self.qOPC.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "write",
				"data":
					{
						"value": self.fsmStorage["part"]["atk"]
					}
			}
		)
	
	def eventSetOPC(self, result):
		try:
			if result == "":
				raise UserWarning("ATK wird geschrieben")
			elif result["status"] == 404:
				raise ResourceWarning(result["error"])
			elif result["data"] == None:
				return "ATK erfolgreich geschrieben"
			elif len(result["data"]) == 0:
				
				raise ResourceWarning("Antwort ist leer")
			else:
				pass
		except Exception as e:
			return e

	def triggerGetAipSettings(self):
		self.qAiP.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "getAipSettings",
				"data":
					{
						"path": self.master.varAiPPath.get()
					}
			}
		)
	
	def eventGetAipSettings(self, result):
		try:
			if result == "":
				raise UserWarning("AiP Einstellungen abfragen")
			elif result["status"] == 404:
				raise ResourceWarning(result["error"])
			elif len(result["data"]) == 0:
				raise ResourceWarning("AiP Antwort ist leer")
			else:
				self.master.varAiPTNR.set(result["data"]["usr"])
				self.master.varAiPPort.set(int(result["data"]["Port"]))
				return "AiP Einstellungen geladen"
			
		except Exception as e:
			return e
			
		
	def triggerGetTerminalInfo(self):
		self.qHYDRA.put(
			{
				"Thread": self.nameQ,
				"Status": "request",
				"do": "getTerminalInfo",
				"data":
					{
						"tnr": self.master.varAiPTNR.get()
					}
			}
		)

	def eventGetTerminalInfo(self, result):
		# Preset & Placeholder
		length = 0
		# Dequeue failed
		# ~ print("TerminalInfo: ", result)
		# Error handle
		try:
			if result["status"] == 404:
				return ResourceWarning(result["error"])
		except Exception as e:
			return e

		try:
			for mnr in result["data"]["Machines"]:
				
				if mnr["MNR"] == self.master.varAiPMNR.get():
					# Save reason per Maschine
					temp = dict(
						mnr = mnr["MNR"],
						reasons = []
					)
					for reason in mnr["ScrapReasons"]:
						print(reason,temp)
						temp["reasons"].append(
							dict(
								number = reason["ReasonNumber"],
								text = reason["ReasonText"]
							)
						)
					# Save reasons for Terminal
					self.fsmStorage["Terminal"]["Reasons"].append(temp)
					length = len(temp["reasons"])
				
			if not length:
				raise ResourceWarning(
					"MNR = %s nicht am TNR = %s vorhanden" % (
							self.master.varAiPMNR.get(),
							self.master.varAiPTNR.get()
						)
					)

			self.fsmState["hydra"] = 0
			return  "%s Fehlergründe geladen" % (length)

		except Exception as e:
			self.fsmState["hydra"] = 1
			print(e.__class__.__name__, e)
			return e

	def eventGetBySecondRFID(self, result):
		try:
			if result["status"] == 200:
				# ~ print(result["data"]["v_los_bestand"])

				# Save article data
				self.fsmStorage["RFID"]["new"] = result["data"]["v_los_bestand"]["dllosnr"]
				self.fsmStorage["part"]["status"] = result["data"]["v_los_bestand"]["klasse"]
				self.fsmStorage["part"]["fault"] = result["data"]["v_los_bestand"]["ausschussgrund"]
				self.fsmStorage["part"]["inspection"] = result["data"]["v_los_bestand"]["status"]



				# Article is scrap
				if self.fsmStorage["part"]["status"] == "A":
					raise ValueError("Artikel ist Ausschuss (%s)"
						% self.fsmStorage["part"]["fault"]
					)
				# Article is in blocked / release stock
				if self.fsmStorage["part"]["inspection"] != "F":
					raise ValueError("Artikel ist nicht Freigegeben (%s)"
						% self.fsmStorage["part"]["inspection"]
					)

				# article is fine
				self.fsmState["hydra"] = 0
				return True

			else:
				raise ValueError(result["error"])

		except Exception as e:
			self.fsmState["hydra"] = 1
			# ~ print("except ",e)
			return e


def main(args):

	root = tk.Tk()
	app = Backend(root)
	root.mainloop()
	return 0

if __name__ == '__main__':
		import sys
		sys.exit(main(sys.argv))
