#!/usr/bin/env python
##
# Copyright 2010-2015 Ghent University
#
# This file is part of mympingpong,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.ugent.be/hpcugent/mympingpong
#
# mympingpong is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# mympingpong is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mympingpong. If not, see <http://www.gnu.org/licenses/>.
##

"""
@author: Stijn De Weirdt (Ghent University)
@author: Jeroen De Clerck (Ghent University)

Generate plots from output from mympingpong.py
"""

import bisect
import sys
from math import sqrt

import h5py
import matplotlib as mp
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.gridspec as gridspec
import numpy as n
from matplotlib.colorbar import Colorbar, make_axes

from vsc.utils.generaloption import simple_option


notset = (None,None)

class PingPongAnalysis(object):

    def __init__(self, logger, latencyscale, latencymask, bins):
        self.log = logger

        self.data = None
        self.count = None
        self.fail = None
        self.consistency = None

        # use multiplication of 10e6 (ie microsec)
        self.scaling = 1e6

        self.meta = None

        self.cmap = None

        self.latencyscale = latencyscale
        self.latencymask = latencymask
        self.bins = bins


    def collecthdf5(self, fn):
        """collects metatags, failures, counters and timingdata from fn"""
        f = h5py.File(fn, 'r')

        self.meta = dict(f.attrs.items())
        self.log.debug("collect meta: %s" % self.meta)     

        if self.meta['failed']:
            self.fail = f['fail'][:]
            self.log.debug("collect fail: %s" % self.fail)

        # http://stackoverflow.com/a/118508
        self.count = n.ma.array(f['data'][...,0])
        self.log.debug("collect count: %s" % self.count)

        data = f['data'][...,1]
        data = data*self.scaling
        data = data/n.where(self.count == 0, 1, self.count)
        self.data = n.ma.array(data)
        self.log.debug("collect data: %s" % data)

        self.consistency = n.ma.array(f['data'][...,2])
        self.log.debug("collect consistency: %s" % self.consistency)

        f.close()

    def setticks(self, nrticks, length, sub):
        """make and set evenly spaced ticks for the subplot, that excludes zero and max"""
        ticks = [0] * nrticks
        for i in range(nrticks):
            ticks[i] = round((i+1) * length/ (nrticks+1))

        sub.set_xticks(ticks)
        sub.set_yticks(ticks)

    def addtext(self, meta, sub, fig):
        self.log.debug("addtext")

        sub.set_axis_off()

        # build a rectangle in axes coords
        left, width = .1, .9
        bottom, height = .1, .9
        right = left + width
        top = bottom + height

        cols = 3
        tags = self.meta.keys()
        nrmeta = len(tags)
        while nrmeta % cols != 0:
            nrmeta += 1
            tags.append(None)
        layout = n.array(tags).reshape(nrmeta/cols, cols)

        for r in xrange(nrmeta/cols):
            for c in xrange(cols):
                m = layout[r][c]
                if not (m and meta.has_key(m)):
                    continue
                val = meta[m]
                unit = ' sec' if m == 'timing' else ''
                sub.text(left+c*width/cols, bottom+r*height/(nrmeta/cols), "%s: %s%s" %
                         (m, val, unit), horizontalalignment='left', verticalalignment='top', transform=sub.transAxes)

    def addlatency(self, data, sub, fig):
        """make and show the main latency graph"""
        maskeddata = n.ma.masked_equal(data, 0)

        if self.latencymask != notset:
            maskeddata = n.ma.masked_outside(maskeddata, self.latencymask[0], self.latencymask[1])

        vmin = maskeddata.min() if self.latencyscale[0] is None else self.latencyscale[0]
        vmax = maskeddata.max() if self.latencyscale[1] is None else self.latencyscale[1]

        cax = sub.imshow(maskeddata, cmap=self.cmap, interpolation='nearest', vmin=vmin, vmax=vmax, origin='lower')
        fig.colorbar(cax)
        self.setticks(7, n.size(data,0), sub)
        sub.set_title(r'Latency ($\mu s$)')

        return vmin, vmax

    def addglobalhistogram(self, data, sub, fig1, vextrema):
        """make and show the histogram"""

        DEFAULTCOLOR = (0.5,0.5,0.5,1)

        # filter out zeros and data that is too small or too large to show with the selected scaling
        d = n.ma.masked_outside(data.ravel(),1/self.scaling, 1.0*self.scaling)
        (nn, binedges, patches) = sub.hist(n.ma.compressed(d), bins=self.bins)

        # We don't want the very first binedge
        binedges = binedges[1:]
        lscale = self.latencyscale
        lmask = self.latencymask
        bisect_edges = lambda x: bisect.bisect(binedges, x)
        vmin_ind, vmax_ind = map(bisect_edges, vextrema)
        colorrange = vmax_ind-vmin_ind

        # create an array of cmapvalues for every bin according to its corresponding cmapvalue from the latency graph
        # if the bin falls outside the mask interval it is colored grey.
        # if the bin falls outside the scale interval, color it dark blue or dark red instead
        colors = [DEFAULTCOLOR]*vmin_ind + [self.cmap(1.*i/colorrange) for i in range(colorrange)] + [DEFAULTCOLOR]*(self.bins-vmax_ind)

        if lscale != notset:
            coloredges = (0, binedges[-1]) if lmask == notset else (lmask[0], lmask[1])
            begin_ind, end_ind = map(bisect_edges, coloredges)
            lscale0_ind, lscale1_ind = map(bisect_edges, lscale)
            if coloredges[0] < lscale[0]:
                begin_ind = bisect.bisect(binedges,coloredges[0])                
                colors = self.overwritecolors(self.cmap(0), colors, begin_ind, lscale0_ind )
            if lscale[1] < coloredges[1]:
                end_ind = bisect.bisect(binedges,coloredges[1])
                colors = self.overwritecolors(self.cmap(1.0), colors, lscale1_ind, end_ind )

        if lmask != notset:
            lmask0_ind, lmask1_ind = map(bisect_edges, lmask)
            if lmask[0] > vextrema[0]:
                colors = self.overwritecolors(DEFAULTCOLOR, colors, end=lmask0_ind)
            if vextrema[1] > lmask[1]:
                colors = self.overwritecolors(DEFAULTCOLOR, colors, begin=lmask1_ind)
        
        # apply colorarray to the bins
        for color, patch in zip(colors,patches):
            patch.set_facecolor(color)

        sub.set_title('Histogram of latency data')
        
        # get the cmapvalue of the color edges (on a scale from 0.0 to 1.0)
        if lscale != notset and lmask != notset:
            coloredges = (float(lmask0_ind-lscale0_ind), float(lmask1_ind-lscale0_ind))
            if lscale1_ind != lscale0_ind
                coloredges = tuple([x/(lscale1_ind-lscale0_ind) for x in coloredges])
        else:
            coloredges = (0.0,1.0)

        return coloredges

    def overwritecolors(self, color, colors, begin=0, end=sys.maxint):
        """will overwrite all elements in the colors array in interval [begin,end] with color"""
        self.log.debug("overwriting %s to %s with %s", begin, end, color)
        return [color if i>=begin and i<end else c for i,c in enumerate(colors)]    
        
    def addmaskedhistogram(self, data, sub, fig1, coloredges):
        """make and show the masked histogram"""

        # filter out zeros and the data that falls outside of the mask interval
        d = n.ma.masked_outside(n.ma.masked_equal(data.ravel(), 0),self.latencymask[0], self.latencymask[1])
        (nn, binedges, patches) = sub.hist(n.ma.compressed(d), bins=self.bins)

        binwidth = (coloredges[1]-coloredges[0]) / self.bins
        self.log.debug("binwidth: %s, color edge 0: %s, color edge 1: %s", binwidth, coloredges[0], coloredges[1])

        # color every bin according to its corresponding cmapvalue from the latency graph
        # if latencyscale has been set, color the bins outside the interval with their corresponding colors instead
        colors = [coloredges[0] + i * binwidth for i in range(self.bins)] 
        self.log.debug('made cmapvalues: %s', colors)

        # apply collorarray to the bins
        for color, patch in zip(colors,patches):
            patch.set_facecolor(self.cmap(color))

        sub.set_title("Histogram of latency data in mask")

    def addsamplesize(self, count, sub, fig):
        self.log.debug("add a sample size graph to the plot")

        maskedcount = n.ma.masked_where(count == 0, count)
        cax = sub.imshow(maskedcount, cmap=self.cmap, interpolation='nearest', vmin = 0, origin='lower')
        cb = fig.colorbar(cax)
        self.setticks(3, n.size(count,0), sub)
        sub.set_title('Pair samples (#)')

    def addconsistency(self, consistency, sub, fig):
        self.log.debug("add a standard deviation graph to the plot")

        maskedconsistency= n.ma.masked_where(consistency == 0, consistency)
        cax = sub.imshow(maskedconsistency, cmap=self.cmap, interpolation='nearest', vmin = 0, origin='lower')
        cb = fig.colorbar(cax)
        self.setticks(3, n.size(consistency,0), sub)
        sub.set_title('standard deviation')

    def plot(self, colormap):
        self.log.debug("plot")

        mp.rcParams.update({'font.size': 15})

        # set colormap
        self.cmap = plt.get_cmap(colormap)
        self.cmap.set_bad(color='grey', alpha=0.25)

        fig1 = plt.figure(figsize=(32,18), dpi=60)

        gs1 = gridspec.GridSpec(10, 10, left=0.02, bottom=0.02, right=0.98, top=0.98, wspace=0.05, hspace=0.6)

        ax1 = plt.subplot(gs1[0:8, 0:5])
        vextrema = self.addlatency(self.data, ax1, fig1)
        ax4 = plt.subplot(gs1[8:10, 0:4])
        coloredges = self.addglobalhistogram(self.data, ax4, fig1, vextrema)

        ax3 = plt.subplot(gs1[0:1, 5:10])
        self.addtext(self.meta, ax3, fig1)
        ax5 = plt.subplot(gs1[1:4, 5:7])
        self.addsamplesize(self.count, ax5, fig1)
        ax6 = plt.subplot(gs1[1:4, 7:9])
        self.addconsistency(self.consistency, ax6, fig1)
        if self.latencymask != notset:
            ax7 = plt.subplot(gs1[8:10, 5:9])
            self.addmaskedhistogram(self.data, ax7, fig1, coloredges)

        fig1.canvas.draw()

        plt.show()


if __name__ == '__main__':

    # dict = {longopt:(help_description,type,action,default_value,shortopt),}
    options = {
        'input': ('set the inputfile', str, 'store', 'test2', 'f'),
        'latencyscale': ('set the minimum and maximum of the latency graph colorscheme',
             'strtuple', 'store', None, 's'
             ),
        'latencymask': ('set the interval of the data that should be plotted in the latency graph, so'
            'any datapoints that falls outside this interval will not be plotted. The colorscheme min and max'
            'will correspond to respectively the lowest and highest value in the remaining data-array',
            'strtuple', 'store', None, 'm'
            ),
        'bins': ('set the amount of bins in the histograms', 'int', 'store', 100, 'b'),
        'colormap': ('set the colormap, for a list of options see http://matplotlib.org/users/colormaps.html', 'string', 'store', 'jet', 'c'),
    }

    go = simple_option(options)

    lscale = map(float, go.options.latencyscale) if go.options.latencyscale else notset
    lmask = map(float, go.options.latencymask) if go.options.latencymask else notset

    ppa = PingPongAnalysis(go.log, lscale, lmask, go.options.bins)
    ppa.collecthdf5(go.options.input)

    ppa.plot(go.options.colormap)
