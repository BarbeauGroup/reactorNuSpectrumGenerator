#TODO
# - Improve upon extrapolation procedure? 5th order polynomial fit to ln of data including errors
# - Put in real reactor data (fractions, power, etc.)
import json
import sys
import numpy
from scipy import interpolate
import os
import math

#############
#Check usage#
#############
if len(sys.argv) != 2:
  print("\nError! No json file specified!")
  print("Usage: python reactorSpectrumGenerator.py <json file>\n")
  sys.exit()

################
#Load JSON file#
################
jsonFile = open(sys.argv[1],"r")
data = json.load(jsonFile)

###########
#Set flags#
###########
useROOT=0 #Set to 1 if "format" is "root" in json file
normalizeSpectrum=0 #Set to 1 in "normalized" is true

###########################
#Check for JSON parameters#
###########################
headings=["spectrum_settings","data_sources","reactor_data","output_settings"]
subHeadings=[
  ["nbins","normalized","emin","emax"],
  ["u235","u238","pu239","pu241"],
  ["type","power","fraction_u235","fraction_u238","fraction_pu239","fraction_pu241"],
  ["format","output_name"]
]
for i,heading in enumerate(headings):
  if not heading in data:
    print("No "+heading+" parameter found in json file, exiting")
    sys.exit()
  for subHeading in subHeadings[i]:
    if not subHeading in data[heading]:
      print("No "+subHeading+" parameter found in parameter "+heading+",exiting")
      sys.exit()

############################
#Try to load ROOT if needed#
############################
if data["output_settings"]["format"]=="root":
  useROOT=1
  try:
      import ROOT
  except ImportError:
      ROOT=None
      print("Error importing ROOT, exiting")
      sys.exit()

#####################################################
#Loads energies and neutrinos/fission from text file#
#####################################################
def loadSpectrum(filename):
  energies=[]
  reactorData=[]
  fname = filename
  if os.path.isdir("fluxData"):
    if os.path.exists("fluxData/"+fname):
      for line in open("fluxData/"+fname):
        if not line.startswith("#"):
          line=line.strip("\n")
          lineParts=line.split(",")
          energies.append(float(lineParts[0]))
          reactorData.append(float(lineParts[1]))
  energies_arr=numpy.array(energies)
  reactorData_arr=numpy.array(reactorData)
  return energies_arr,reactorData_arr

#########################################################
#Interpolate/Extrapolate to get data at desired energies#
#########################################################
def fillInData(energies,data,desired_energies):
  #Holds interpolated/extrapolated data
  newData=[]

  #Make an interpolation function
  f = interpolate.interp1d(energies,data,kind='cubic')
  
  #Fit a 5th order polynomial to the log of the existing data to extrapolate
  #logData=numpy.log(data)
  #reversed_coeffs=numpy.polyfit(energies,data,5)
  #coeffs=reversed_coeffs[::-1]
  
  #Do linear fit to lowest four data points
  if len(energies) < 4:
    print("\nLess than 4 data points requested, extrapolation routine will fail! Exiting\n")
    sys.exit()
  lowEnergies=energies[0:4]
  lowData=data[0:4]
  rev_lowCoeffs=numpy.polyfit(lowEnergies,lowData,1)
  lowCoeffs=rev_lowCoeffs[::-1]
  
  #Do linear fit to upper 4 data points
  highEnergies=energies[-4:]
  highData=data[-4:]
  rev_highCoeffs=numpy.polyfit(highEnergies,highData,1)
  highCoeffs=rev_highCoeffs[::-1]
  
  #Step through desired energies, if outside range extrapolate and add to data array
  for desired_energy in desired_energies:
    #if desired_energy < numpy.amin(energies) or desired_energy > numpy.amax(energies):
    #  dataToSum=[coeffs[i]*math.pow(desired_energy,i) for i in range(0,len(coeffs))]
    #  sum=numpy.sum(dataToSum)
    #  dataVal=math.exp(sum)
    if desired_energy < numpy.amin(energies):
      dataToSum=[lowCoeffs[i]*math.pow(desired_energy,i) for i in range(0,len(lowCoeffs))]
      dataVal=numpy.sum(dataToSum)
    elif desired_energy > numpy.amax(energies):
      dataToSum=[highCoeffs[i]*math.pow(desired_energy,i) for i in range(0,len(highCoeffs))]
      dataVal=numpy.sum(dataToSum)
    elif desired_energy in energies:
      idx=numpy.where(energies == desired_energy)
      dataVal=data[idx][0]
    else:
      dataVal=f(desired_energy)
    
    #Make sure we don't have negative flux
    if dataVal<0:
      dataVal=0
    newData.append(dataVal)

  newData_arr=numpy.array(newData)
  return newData_arr

####################
#Makes the spectrum#
####################
def makeSpectrum(energies,dataSets,fractions):
  #Will hold spectrum
  spectrum=numpy.array([0 for i in energies])
  #Scale source data by fraction, add
  for i,fraction in enumerate(fractions):
    dataSets[i] = dataSets[i]*fraction
    spectrum=numpy.add(spectrum,dataSets[i])
  #Return combined spectrum
  return spectrum

###################################
#Write the spectrum to a Root file#
###################################
def makeRootFile(energies,spectrum,yaxisTitle):
  print("\nMaking root file "+data["output_settings"]["output_name"])
  outFile=ROOT.TFile(data["output_settings"]["output_name"],"RECREATE")
  hist=ROOT.TH1D("hist","Spectrum;Energy (MeV);"+yaxisTitle,nbins,numpy.min(energies),numpy.max(energies))
  for i,energy in enumerate(energies):
    bin=hist.FindBin(energy)
    hist.SetBinContent(bin,spectrum[i])
  hist.Write()
  
  #Draw
  c1=ROOT.TCanvas()
  hist.Draw()
  c1.SetLogy()
  c1.Modified()
  c1.Update()
  try:
    input("Press enter to continue")
  except SyntaxError:
    pass
    
  outFile.Close()

###################################
#Write the spectrum to a text file#
###################################
def makeTextFile(energies,spectrum):
  print("\nMaking text file "+data["output_settings"]["output_name"])
  outFile=open(data["output_settings"]["output_name"],"w")
  for i,energy in enumerate(energies):
    line="{0:.3f}".format(energy)+","+'{0:.6f}'.format(spectrum[i])
    if i != len(energies)-1:
      line=line+"\n"
    outFile.write(line)
  outFile.close()

###########
#Main code#
###########
#Make energies array
emin=data["spectrum_settings"]["emin"]
emax=data["spectrum_settings"]["emax"]
nbins=data["spectrum_settings"]["nbins"]
energies = numpy.linspace(emin,emax,nbins)

#Load and normalize fractions
fractions=[]
fractions.append(data["reactor_data"]["fraction_u235"])
fractions.append(data["reactor_data"]["fraction_u238"])
fractions.append(data["reactor_data"]["fraction_pu239"])
fractions.append(data["reactor_data"]["fraction_pu241"])
fractionSum=sum(fractions)
fractions_arr=numpy.array([i/float(fractionSum) for i in fractions])

#Load data sets
dataEnergies=[]
dataSets=[]
isotopes=subHeadings[1]
for isotope in isotopes:
  print("Loading "+str(data["data_sources"][isotope]))
  dataEnergy,dataSet = loadSpectrum(data["data_sources"][isotope])
  if fractions_arr[i] > 0:
    if numpy.amin(dataEnergy) > emin or numpy.amax(dataEnergy) < emax:
      print("\nData set "+str(data["data_sources"][isotope])+" has range of ("
        +str(numpy.amin(dataEnergy))+","+str(numpy.amax(dataEnergy))+
        "), does not cover requested energy range of ("+str(emin)+","+str(emax)+")")
      print("Extrapolating, results may not be reliable!\n")
  dataSets.append(fillInData(dataEnergy,dataSet,energies))

#Make spectrum
spectrum = makeSpectrum(energies,dataSets,fractions_arr)

#Do normalization
if data["spectrum_settings"]["normalized"]=="pdf":
  spectrumSum=sum(spectrum)
  spectrum=[i/float(spectrumSum) for i in spectrum]
  yaxisTitle="Normalized Counts"
elif data["spectrum_settings"]["normalized"]=="GW":
  power=data["reactor_data"]["power"]
  fissionsPerW=3.1*math.pow(10,10)
  fissionsPerGW=fissionsPerW*math.pow(10,9)
  spectrum=fissionsPerGW*spectrum
  yaxisTitle="Neutrinos"
else:
  yaxisTitle="Neutrinos/fission"

#Make output
if useROOT==1:
  makeRootFile(energies,spectrum,yaxisTitle)
else:
  makeTextFile(energies,spectrum)

