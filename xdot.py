#!/usr/bin/env python
#
# Copyright 2008 Jose Fonseca
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

'''Visualize dot graphs via the xdot format.'''

__author__ = "Jose Fonseca"

__version__ = "0.3"


import os
import sys
import subprocess
import math
import colorsys
import time

import gobject
import gtk
import gtk.gdk
import gtk.keysyms
import cairo
import pango
import pangocairo

import pydot

if pydot.__version__ != '0.9.10':
    sys.stderr('pydot version 0.9.10 required, but version %s found\n' % pydot.__version__)


# See http://www.graphviz.org/pub/scm/graphviz-cairo/plugin/cairo/gvrender_cairo.c

# For pygtk inspiration and guidance see:
# - http://mirageiv.berlios.de/
# - http://comix.sourceforge.net/


class Pen:
    """Store pen attributes."""

    def __init__(self):
        # set default attributes
        self.color = (0.0, 0.0, 0.0, 1.0)
        self.fillcolor = (0.0, 0.0, 0.0, 1.0)
        self.linewidth = 1.0
        self.fontsize = 14.0
        self.fontname = "Times-Roman"
        self.dash = ()

    def copy(self):
        """Create a copy of this pen."""
        pen = Pen()
        pen.__dict__ = self.__dict__.copy()
        return pen

    def highlighted(self):
        pen = self.copy()
        pen.color = (1, 0, 0, 1)
        pen.fillcolor = (1, .8, .8, 1)
        return pen


class Shape:
    """Abstract base class for all the drawing shapes."""

    def __init__(self):
        pass

    def draw(self, cr, highlight=False):
        """Draw this shape with the given cairo context"""
        raise NotImplementedError

    def select_pen(self, highlight):
        if highlight:
            if not hasattr(self, 'highlight_pen'):
                self.highlight_pen = self.pen.highlighted()
            return self.highlight_pen
        else:
            return self.pen


class TextShape(Shape):

    #fontmap = pangocairo.CairoFontMap()
    #fontmap.set_resolution(72)
    #context = fontmap.create_context()

    LEFT, CENTER, RIGHT = -1, 0, 1

    def __init__(self, pen, x, y, j, w, t):
        Shape.__init__(self)
        self.pen = pen.copy()
        self.x = x
        self.y = y
        self.j = j
        self.w = w
        self.t = t

    def draw(self, cr, highlight=False):

        try:
            layout = self.layout
        except AttributeError:
            layout = cr.create_layout()

            # set font options
            # see http://lists.freedesktop.org/archives/cairo/2007-February/009688.html
            context = layout.get_context()
            fo = cairo.FontOptions()
            fo.set_antialias(cairo.ANTIALIAS_DEFAULT)
            fo.set_hint_style(cairo.HINT_STYLE_NONE)
            fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
            pangocairo.context_set_font_options(context, fo)

            # set font
            font = pango.FontDescription()
            font.set_family(self.pen.fontname)
            font.set_absolute_size(self.pen.fontsize*pango.SCALE)
            layout.set_font_description(font)

            # set text
            layout.set_text(self.t)

            # cache it
            self.layout = layout
        else:
            cr.update_layout(layout)

        descent = 2 # XXX get descender from font metrics

        width, height = layout.get_size()
        width = float(width)/pango.SCALE
        height = float(height)/pango.SCALE
        # we know the width that dot thinks this text should have
        # we do not necessarily have a font with the same metrics
        # scale it so that the text fits inside its box
        if width > self.w:
            f = self.w / width
            width = self.w # equivalent to width *= f
            height *= f
            descent *= f
        else:
            f = 1.0

        if self.j == self.LEFT:
            x = self.x
        elif self.j == self.CENTER:
            x = self.x - 0.5*width
        elif self.j == self.RIGHT:
            x = self.x - width
        else:
            assert 0

        y = self.y - height + descent

        cr.move_to(x, y)

        cr.save()
        cr.scale(f, f)
        cr.set_source_rgba(*self.select_pen(highlight).color)
        cr.show_layout(layout)
        cr.restore()

        if 0: # DEBUG
            # show where dot thinks the text should appear
            cr.set_source_rgba(1, 0, 0, .9)
            if self.j == self.LEFT:
                x = self.x
            elif self.j == self.CENTER:
                x = self.x - 0.5*self.w
            elif self.j == self.RIGHT:
                x = self.x - self.w
            cr.move_to(x, self.y)
            cr.line_to(x+self.w, self.y)
            cr.stroke()


class EllipseShape(Shape):

    def __init__(self, pen, x0, y0, w, h, filled=False):
        Shape.__init__(self)
        self.pen = pen.copy()
        self.x0 = x0
        self.y0 = y0
        self.w = w
        self.h = h
        self.filled = filled

    def draw(self, cr, highlight=False):
        cr.save()
        cr.translate(self.x0, self.y0)
        cr.scale(self.w, self.h)
        cr.move_to(1.0, 0.0)
        cr.arc(0.0, 0.0, 1.0, 0, 2.0*math.pi)
        cr.restore()
        pen = self.select_pen(highlight)
        if self.filled:
            cr.set_source_rgba(*pen.fillcolor)
            cr.fill()
        else:
            cr.set_dash(pen.dash)
            cr.set_line_width(pen.linewidth)
            cr.set_source_rgba(*pen.color)
            cr.stroke()


class PolygonShape(Shape):

    def __init__(self, pen, points, filled=False):
        Shape.__init__(self)
        self.pen = pen.copy()
        self.points = points
        self.filled = filled

    def draw(self, cr, highlight=False):
        x0, y0 = self.points[-1]
        cr.move_to(x0, y0)
        for x, y in self.points:
            cr.line_to(x, y)
        cr.close_path()
        pen = self.select_pen(highlight)
        if self.filled:
            cr.set_source_rgba(*pen.fillcolor)
            cr.fill_preserve()
            cr.fill()
        else:
            cr.set_dash(pen.dash)
            cr.set_line_width(pen.linewidth)
            cr.set_source_rgba(*pen.color)
            cr.stroke()


class BezierShape(Shape):

    def __init__(self, pen, points):
        Shape.__init__(self)
        self.pen = pen.copy()
        self.points = points

    def draw(self, cr, highlight=False):
        x0, y0 = self.points[0]
        cr.move_to(x0, y0)
        for i in xrange(1, len(self.points), 3):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i + 1]
            x3, y3 = self.points[i + 2]
            cr.curve_to(x1, y1, x2, y2, x3, y3)
        pen = self.select_pen(highlight)
        cr.set_dash(pen.dash)
        cr.set_line_width(pen.linewidth)
        cr.set_source_rgba(*pen.color)
        cr.stroke()


class CompoundShape(Shape):

    def __init__(self, shapes):
        Shape.__init__(self)
        self.shapes = shapes

    def draw(self, cr, highlight=False):
        for shape in self.shapes:
            shape.draw(cr, highlight=highlight)


class Url(object):

    def __init__(self, item, url, highlight=None):
        self.item = item
        self.url = url
        if highlight is None:
            highlight = set([item])
        self.highlight = highlight


class Jump(object):

    def __init__(self, item, x, y, highlight=None):
        self.item = item
        self.x = x
        self.y = y
        if highlight is None:
            highlight = set([item])
        self.highlight = highlight


class Element(CompoundShape):
    """Base class for graph nodes and edges."""

    def __init__(self, shapes):
        CompoundShape.__init__(self, shapes)

    def get_url(self, x, y):
        return None

    def get_jump(self, x, y):
        return None


class Node(Element):

    def __init__(self, x, y, w, h, shapes, url):
        Element.__init__(self, shapes)

        self.x = x
        self.y = y

        self.x1 = x - 0.5*w
        self.y1 = y - 0.5*h
        self.x2 = x + 0.5*w
        self.y2 = y + 0.5*h

        self.url = url

    def is_inside(self, x, y):
        return self.x1 <= x and x <= self.x2 and self.y1 <= y and y <= self.y2

    def get_url(self, x, y):
        if self.url is None:
            return None
        #print (x, y), (self.x1, self.y1), "-", (self.x2, self.y2)
        if self.is_inside(x, y):
            return Url(self, self.url)
        return None

    def get_jump(self, x, y):
        if self.is_inside(x, y):
            return Jump(self, self.x, self.y)
        return None


def square_distance(x1, y1, x2, y2):
    deltax = x2 - x1
    deltay = y2 - y1
    return deltax*deltax + deltay*deltay


class Edge(Element):

    def __init__(self, src, dst, points, shapes):
        Element.__init__(self, shapes)
        self.src = src
        self.dst = dst
        self.points = points

    RADIUS = 10

    def get_jump(self, x, y):
        if square_distance(x, y, *self.points[0]) <= self.RADIUS*self.RADIUS:
            return Jump(self, self.dst.x, self.dst.y, highlight=set([self, self.dst]))
        if square_distance(x, y, *self.points[-1]) <= self.RADIUS*self.RADIUS:
            return Jump(self, self.src.x, self.src.y, highlight=set([self, self.src]))
        return None


class Graph(Shape):

    def __init__(self, width=1, height=1, nodes=(), edges=()):
        Shape.__init__(self)

        self.width = width
        self.height = height
        self.nodes = nodes
        self.edges = edges

    def get_size(self):
        return self.width, self.height

    def draw(self, cr, highlight_items=None):
        if highlight_items is None:
            highlight_items = ()
        cr.set_source_rgba(0.0, 0.0, 0.0, 1.0)

        cr.set_line_cap(cairo.LINE_CAP_BUTT)
        cr.set_line_join(cairo.LINE_JOIN_MITER)

        for edge in self.edges:
            edge.draw(cr, highlight=(edge in highlight_items))
        for node in self.nodes:
            node.draw(cr, highlight=(node in highlight_items))

    def get_url(self, x, y):
        for node in self.nodes:
            url = node.get_url(x, y)
            if url is not None:
                return url
        return None

    def get_jump(self, x, y):
        for edge in self.edges:
            jump = edge.get_jump(x, y)
            if jump is not None:
                return jump
        for node in self.nodes:
            jump = node.get_jump(x, y)
            if jump is not None:
                return jump
        return None


class XDotAttrParser:
    """Parser for xdot drawing attributes.
    See also:
    - http://www.graphviz.org/doc/info/output.html#d:xdot
    """

    def __init__(self, parser, buf):
        self.parser = parser
        self.buf = self.unescape(buf)
        self.pos = 0

    def __nonzero__(self):
        return self.pos < len(self.buf)

    def unescape(self, buf):
        buf = buf.replace('\\"', '"')
        buf = buf.replace('\\n', '\n')
        return buf

    def read_code(self):
        pos = self.buf.find(" ", self.pos)
        res = self.buf[self.pos:pos]
        self.pos = pos + 1
        while self.pos < len(self.buf) and self.buf[self.pos].isspace():
            self.pos += 1
        return res

    def read_number(self):
        return int(self.read_code())

    def read_float(self):
        return float(self.read_code())

    def read_point(self):
        x = self.read_number()
        y = self.read_number()
        return self.transform(x, y)

    def read_text(self):
        num = self.read_number()
        pos = self.buf.find("-", self.pos) + 1
        self.pos = pos + num
        res = self.buf[pos:self.pos]
        while self.pos < len(self.buf) and self.buf[self.pos].isspace():
            self.pos += 1
        return res

    def read_polygon(self):
        n = self.read_number()
        p = []
        for i in range(n):
            x, y = self.read_point()
            p.append((x, y))
        return p

    def read_color(self, fallback=(0,0,0,1)):
        # See http://www.graphviz.org/doc/info/attrs.html#k:color
        c = self.read_text()
        c1 = c[:1]
        if c1 == '#':
            hex2float = lambda h: float(int(h, 16)/255.0)
            r = hex2float(c[1:3])
            g = hex2float(c[3:5])
            b = hex2float(c[5:7])
            try:
                a = hex2float(c[7:9])
            except (IndexError, ValueError):
                a = 1.0
            return r, g, b, a
        elif c1.isdigit() or c1 == ".":
            # "H,S,V" or "H S V" or "H, S, V" or any other variation
            h, s, v = map(float, c.replace(",", " ").split())
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            a = 1.0
            return r, g, b, a
        else:
            try:
                color = gtk.gdk.color_parse(c)
            except ValueError:
                sys.stderr.write("unknown color '%s'\n" % c)
                return fallback
            s = 1.0/65535.0
            r = color.red*s
            g = color.green*s
            b = color.blue*s
            a = 1.0
            return r, g, b, a

    def parse(self):
        shapes = []
        pen = Pen()
        s = self

        while s:
            op = s.read_code()
            if op == "c":
                pen.color = s.read_color(fallback=pen.color)
            elif op == "C":
                pen.fillcolor = s.read_color(fallback=pen.fillcolor)
            elif op == "S":
                style = s.read_text()
                if style.startswith("setlinewidth("):
                    lw = style.split("(")[1].split(")")[0]
                    pen.linewidth = float(lw)
                elif style == "solid":
                    pen.dash = ()
                elif style == "dashed":
                    pen.dash = (6, )       # 6pt on, 6pt off
            elif op == "F":
                pen.fontsize = s.read_float()
                pen.fontname = s.read_text()
            elif op == "T":
                x, y = s.read_point()
                j = s.read_number()
                w = s.read_number()
                t = s.read_text()
                shapes.append(TextShape(pen, x, y, j, w, t))
            elif op == "E":
                x0, y0 = s.read_point()
                w = s.read_number()
                h = s.read_number()
                # xdot uses this to mean "draw a filled shape with an outline"
                shapes.append(EllipseShape(pen, x0, y0, w, h, filled=True))
                shapes.append(EllipseShape(pen, x0, y0, w, h))
            elif op == "e":
                x0, y0 = s.read_point()
                w = s.read_number()
                h = s.read_number()
                shapes.append(EllipseShape(pen, x0, y0, w, h))
            elif op == "B":
                p = self.read_polygon()
                shapes.append(BezierShape(pen, p))
            elif op == "P":
                p = self.read_polygon()
                # xdot uses this to mean "draw a filled shape with an outline"
                shapes.append(PolygonShape(pen, p, filled=True))
                shapes.append(PolygonShape(pen, p))
            elif op == "p":
                p = self.read_polygon()
                shapes.append(PolygonShape(pen, p))
            else:
                sys.stderr.write("unknown xdot opcode '%s'\n" % op)
                break
        return shapes

    def transform(self, x, y):
        return self.parser.transform(x, y)


class GraphParseError(Exception):
    pass


class XDotParser:

    def __init__(self, xdotcode):
        self.xdotcode = xdotcode

    def parse(self):
        graph = pydot.graph_from_dot_data(self.xdotcode)

        if graph.bb is None:
            return GraphParseError()

        xmin, ymin, xmax, ymax = map(int, graph.bb.split(","))

        self.xoffset = -xmin
        self.yoffset = -ymax
        self.xscale = 1.0
        self.yscale = -1.0
        # FIXME: scale from points to pixels

        width = xmax - xmin
        height = ymax - ymin

        nodes = []
        edges = []
        node_by_name = {}

        for node in graph.get_node_list():
            if node.pos is None:
                continue
            x, y = self.parse_node_pos(node.pos)
            w = float(node.width)*72
            h = float(node.height)*72
            shapes = []
            for attr in ("_draw_", "_ldraw_"):
                if hasattr(node, attr):
                    parser = XDotAttrParser(self, getattr(node, attr))
                    shapes.extend(parser.parse())
            url = node.URL
            my_node = Node(x, y, w, h, shapes, url)
            node_name = node.get_name().strip('"') # XXX
            node_by_name[node_name] = my_node
            if shapes:
                nodes.append(my_node)

        for edge in graph.get_edge_list():
            if edge.pos is None:
                continue
            points = self.parse_edge_pos(edge.pos)
            shapes = []
            for attr in ("_draw_", "_ldraw_", "_hdraw_", "_tdraw_", "_hldraw_", "_tldraw_"):
                if hasattr(edge, attr):
                    parser = XDotAttrParser(self, getattr(edge, attr))
                    shapes.extend(parser.parse())
            if shapes:
                src = node_by_name[edge.get_source()]
                dst = node_by_name[edge.get_destination()]
                edges.append(Edge(src, dst, points, shapes))

        return Graph(width, height, nodes, edges)

    def parse_node_pos(self, pos):
        x, y = pos.split(",")
        return self.transform(float(x), float(y))

    def parse_edge_pos(self, pos):
        points = []
        for entry in pos.split(' '):
            fields = entry.split(',')
            try:
                x, y = fields
            except ValueError:
                # TODO: handle start/end points
                continue
            else:
                points.append(self.transform(float(x), float(y)))
        return points

    def transform(self, x, y):
        # XXX: this is not the right place for this code
        x = (x + self.xoffset)*self.xscale
        y = (y + self.yoffset)*self.yscale
        return x, y


class Animation(object):

    step = 0.03 # seconds

    def __init__(self, dot_widget):
        self.dot_widget = dot_widget
        self.timeout_id = None

    def start(self):
        self.timeout_id = gobject.timeout_add(int(self.step * 1000), self.tick)

    def stop(self):
        self.dot_widget.animation = NoAnimation(self.dot_widget)
        if self.timeout_id is not None:
            gobject.source_remove(self.timeout_id)
            self.timeout_id = None

    def tick(self):
        self.stop()


class NoAnimation(Animation):

    def start(self):
        pass

    def stop(self):
        pass


class LinearAnimation(Animation):

    duration = 0.6

    def start(self):
        self.started = time.time()
        Animation.start(self)

    def tick(self):
        t = (time.time() - self.started) / self.duration
        self.animate(max(0, min(t, 1)))
        return (t < 1)

    def animate(self, t):
        pass


class MoveToAnimation(LinearAnimation):

    def __init__(self, dot_widget, target_x, target_y):
        Animation.__init__(self, dot_widget)
        self.source_x = dot_widget.x
        self.source_y = dot_widget.y
        self.target_x = target_x
        self.target_y = target_y

    def animate(self, t):
        sx, sy = self.source_x, self.source_y
        tx, ty = self.target_x, self.target_y
        self.dot_widget.x = tx * t + sx * (1-t)
        self.dot_widget.y = ty * t + sy * (1-t)
        self.dot_widget.queue_draw()


class ZoomToAnimation(MoveToAnimation):

    def __init__(self, dot_widget, target_x, target_y):
        MoveToAnimation.__init__(self, dot_widget, target_x, target_y)
        self.source_zoom = dot_widget.zoom_ratio
        self.target_zoom = self.source_zoom
        self.extra_zoom = 0

        middle_zoom = 0.5 * (self.source_zoom + self.target_zoom)

        distance = math.hypot(self.source_x - self.target_x,
                              self.source_y - self.target_y)
        rect = self.dot_widget.get_allocation()
        visible = min(rect.width, rect.height) / self.dot_widget.zoom_ratio
        visible *= 0.9
        if distance > 0:
            desired_middle_zoom = visible / distance
            self.extra_zoom = min(0, 4 * (desired_middle_zoom - middle_zoom))

    def animate(self, t):
        a, b, c = self.source_zoom, self.extra_zoom, self.target_zoom
        self.dot_widget.zoom_ratio = c*t + b*t*(1-t) + a*(1-t)
        MoveToAnimation.animate(self, t)


class DragAction(object):

    def __init__(self, dot_widget):
        self.dot_widget = dot_widget

    def on_button_press(self, event):
        self.startmousex = self.prevmousex = event.x
        self.startmousey = self.prevmousey = event.y
        self.start()

    def on_motion_notify(self, event):
        deltax = self.prevmousex - event.x
        deltay = self.prevmousey - event.y
        self.drag(deltax, deltay)
        self.prevmousex = event.x
        self.prevmousey = event.y

    def on_button_release(self, event):
        self.stopmousex = event.x
        self.stopmousey = event.y
        self.stop()

    def draw(self, cr):
        pass

    def start(self):
        pass

    def drag(self, deltax, deltay):
        pass

    def stop(self):
        pass

    def abort(self):
        pass


class NullAction(DragAction):

    def on_motion_notify(self, event):
        dot_widget = self.dot_widget
        item = dot_widget.get_url(event.x, event.y)
        if item is None:
            item = dot_widget.get_jump(event.x, event.y)
        if item is not None:
            dot_widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))
            dot_widget.set_highlight(item.highlight)
        else:
            dot_widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.ARROW))
            dot_widget.set_highlight(None)


class PanAction(DragAction):

    def start(self):
        self.dot_widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.FLEUR))

    def drag(self, deltax, deltay):
        self.dot_widget.x += deltax / self.dot_widget.zoom_ratio
        self.dot_widget.y += deltay / self.dot_widget.zoom_ratio
        self.dot_widget.queue_draw()

    def stop(self):
        self.dot_widget.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.ARROW))

    abort = stop


class ZoomAction(DragAction):

    def drag(self, deltax, deltay):
        self.dot_widget.zoom_ratio *= 1.005 ** (deltax + deltay)
        self.dot_widget.queue_draw()

    def stop(self):
        self.dot_widget.queue_draw()


class ZoomAreaAction(DragAction):

    def drag(self, deltax, deltay):
        self.dot_widget.queue_draw()

    def draw(self, cr):
        cr.save()
        cr.set_source_rgba(.5, .5, 1.0, 0.25)
        cr.rectangle(self.startmousex, self.startmousey,
                     self.prevmousex - self.startmousex,
                     self.prevmousey - self.startmousey)
        cr.fill()
        cr.set_source_rgba(.5, .5, 1.0, 1.0)
        cr.set_line_width(1)
        cr.rectangle(self.startmousex - .5, self.startmousey - .5,
                     self.prevmousex - self.startmousex + 1,
                     self.prevmousey - self.startmousey + 1)
        cr.stroke()
        cr.restore()

    def stop(self):
        x1, y1 = self.dot_widget.window2graph(self.startmousex,
                                              self.startmousey)
        x2, y2 = self.dot_widget.window2graph(self.stopmousex,
                                              self.stopmousey)
        self.dot_widget.zoom_to_area(x1, y1, x2, y2)

    def abort(self):
        self.dot_widget.queue_draw()


class DotWidget(gtk.DrawingArea):
    """PyGTK widget that draws dot graphs."""

    __gsignals__ = {
        'expose-event': 'override',
        'clicked' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gtk.gdk.Event))
    }

    def __init__(self):
        gtk.DrawingArea.__init__(self)

        self.graph = Graph()

        self.set_flags(gtk.CAN_FOCUS)

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
        self.connect("button-press-event", self.on_area_button_press)
        self.connect("button-release-event", self.on_area_button_release)
        self.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
        self.connect("motion-notify-event", self.on_area_motion_notify)
        self.connect("scroll-event", self.on_area_scroll_event)

        self.connect('key-press-event', self.on_key_press_event)

        self.x, self.y = 0.0, 0.0
        self.zoom_ratio = 1.0
        self.animation = NoAnimation(self)
        self.drag_action = NullAction(self)
        self.presstime = None
        self.highlight = None

    def set_dotcode(self, dotcode, filename='<stdin>'):
        p = subprocess.Popen(
            ['dot', '-Txdot'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            shell=False,
            universal_newlines=True
        )
        xdotcode = p.communicate(dotcode)[0]
        try:
            self.set_xdotcode(xdotcode)
        except GraphParseError, e:
            msg = "Could not parse %s, is it a valid dot file?" % filename
            error_dlg = gtk.MessageDialog(type=gtk.MESSAGE_ERROR,
                                          message_format=msg,
                                          buttons=gtk.BUTTONS_OK)
            error_dlg.set_title('Dot Viewer')
            error_dlg.run()
            error_dlg.destroy()
            return False
        else:
            return True

    def set_xdotcode(self, xdotcode):
        #print xdotcode
        parser = XDotParser(xdotcode)
        self.graph = parser.parse()
        self.zoom_image(self.zoom_ratio, center=True)

    def do_expose_event(self, event):
        cr = self.window.cairo_create()

        # set a clip region for the expose event
        cr.rectangle(
            event.area.x, event.area.y,
            event.area.width, event.area.height
        )
        cr.clip()

        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.paint()

        cr.save()
        rect = self.get_allocation()
        cr.translate(0.5*rect.width, 0.5*rect.height)
        cr.scale(self.zoom_ratio, self.zoom_ratio)
        cr.translate(-self.x, -self.y)

        self.graph.draw(cr, highlight_items=self.highlight)
        cr.restore()

        self.drag_action.draw(cr)

        return False

    def get_current_pos(self):
        return self.x, self.y

    def set_current_pos(self, x, y):
        self.x = x
        self.y = y
        self.queue_draw()

    def set_highlight(self, items):
        if self.highlight != items:
            self.highlight = items
            self.queue_draw()

    def zoom_image(self, zoom_ratio, center=False):
        if center:
            self.x = self.graph.width/2
            self.y = self.graph.height/2
        self.zoom_ratio = zoom_ratio
        self.queue_draw()

    def zoom_to_area(self, x1, y1, x2, y2):
        rect = self.get_allocation()
        width = abs(x1 - x2)
        height = abs(y1 - y2)
        self.zoom_ratio = min(
            float(rect.width)/float(width),
            float(rect.height)/float(height)
        )
        self.x = (x1 + x2) / 2
        self.y = (y1 + y2) / 2
        self.queue_draw()

    def zoom_to_fit(self):
        rect = self.get_allocation()
        rect.x += self.ZOOM_TO_FIT_MARGIN
        rect.y += self.ZOOM_TO_FIT_MARGIN
        rect.width -= 2 * self.ZOOM_TO_FIT_MARGIN
        rect.height -= 2 * self.ZOOM_TO_FIT_MARGIN
        zoom_ratio = min(
            float(rect.width)/float(self.graph.width),
            float(rect.height)/float(self.graph.height)
        )
        self.zoom_image(zoom_ratio, center=True)

    ZOOM_INCREMENT = 1.25
    ZOOM_TO_FIT_MARGIN = 12

    def on_zoom_in(self, action):
        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

    def on_zoom_out(self, action):
        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

    def on_zoom_fit(self, action):
        self.zoom_to_fit()

    def on_zoom_100(self, action):
        self.zoom_image(1.0)

    POS_INCREMENT = 100

    def on_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Left:
            self.x -= self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Right:
            self.x += self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Up:
            self.y -= self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Down:
            self.y += self.POS_INCREMENT/self.zoom_ratio
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Page_Up:
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Page_Down:
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
            self.queue_draw()
            return True
        if event.keyval == gtk.keysyms.Escape:
            self.drag_action.abort()
            self.drag_action = NullAction(self)
            return True
        return False

    def get_drag_action(self, event):
        state = event.state
        if event.button in (1, 2): # left or middle button
            if state & gtk.gdk.CONTROL_MASK:
                return ZoomAction
            elif state & gtk.gdk.SHIFT_MASK:
                return ZoomAreaAction
            else:
                return PanAction
        return NullAction

    def on_area_button_press(self, area, event):
        self.animation.stop()
        self.drag_action.abort()
        action_type = self.get_drag_action(event)
        self.drag_action = action_type(self)
        self.drag_action.on_button_press(event)
        self.presstime = time.time()
        self.pressx = event.x
        self.pressy = event.y
        return False

    def is_click(self, event, click_fuzz=4, click_timeout=1.0):
        assert event.type == gtk.gdk.BUTTON_RELEASE
        if self.presstime is None:
            # got a button release without seeing the press?
            return False
        # XXX instead of doing this complicated logic, shouldn't we listen
        # for gtk's clicked event instead?
        deltax = self.pressx - event.x
        deltay = self.pressy - event.y
        return (time.time() < self.presstime + click_timeout
                and math.hypot(deltax, deltay) < click_fuzz)

    def on_area_button_release(self, area, event):
        self.drag_action.on_button_release(event)
        self.drag_action = NullAction(self)
        if event.button == 1 and self.is_click(event):
            x, y = int(event.x), int(event.y)
            url = self.get_url(x, y)
            if url is not None:
                self.emit('clicked', unicode(url.url), event)
            else:
                jump = self.get_jump(x, y)
                if jump is not None:
                    self.animate_to(jump.x, jump.y)

            return True
        if event.button == 1 or event.button == 2:
            return True
        return False

    def on_area_scroll_event(self, area, event):
        if event.direction == gtk.gdk.SCROLL_UP:
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
            return True
        if event.direction == gtk.gdk.SCROLL_DOWN:
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
            return True
        return False

    def on_area_motion_notify(self, area, event):
        self.drag_action.on_motion_notify(event)
        return True

    def animate_to(self, x, y):
        self.animation = ZoomToAnimation(self, x, y)
        self.animation.start()

    def window2graph(self, x, y):
        rect = self.get_allocation()
        x -= 0.5*rect.width
        y -= 0.5*rect.height
        x /= self.zoom_ratio
        y /= self.zoom_ratio
        x += self.x
        y += self.y
        return x, y

    def get_url(self, x, y):
        x, y = self.window2graph(x, y)
        return self.graph.get_url(x, y)

    def get_jump(self, x, y):
        x, y = self.window2graph(x, y)
        return self.graph.get_jump(x, y)


class DotWindow(gtk.Window):

    ui = '''
    <ui>
        <toolbar name="ToolBar">
            <toolitem action="Open"/>
            <separator/>
            <toolitem action="ZoomIn"/>
            <toolitem action="ZoomOut"/>
            <toolitem action="ZoomFit"/>
            <toolitem action="Zoom100"/>
        </toolbar>
    </ui>
    '''

    def __init__(self):
        gtk.Window.__init__(self)

        self.graph = Graph()

        window = self

        window.set_title('Dot Viewer')
        window.set_default_size(512, 512)
        vbox = gtk.VBox()
        window.add(vbox)

        self.widget = DotWidget()

        # Create a UIManager instance
        uimanager = self.uimanager = gtk.UIManager()

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = gtk.ActionGroup('Actions')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions((
            ('Open', gtk.STOCK_OPEN, None, None, None, self.on_open),
            ('ZoomIn', gtk.STOCK_ZOOM_IN, None, None, None, self.widget.on_zoom_in),
            ('ZoomOut', gtk.STOCK_ZOOM_OUT, None, None, None, self.widget.on_zoom_out),
            ('ZoomFit', gtk.STOCK_ZOOM_FIT, None, None, None, self.widget.on_zoom_fit),
            ('Zoom100', gtk.STOCK_ZOOM_100, None, None, None, self.widget.on_zoom_100),
        ))

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI descrption
        uimanager.add_ui_from_string(self.ui)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        vbox.pack_start(toolbar, False)

        vbox.pack_start(self.widget)

        self.set_focus(self.widget)

        self.show_all()

    def set_dotcode(self, dotcode, filename='<stdin>'):
        if self.widget.set_dotcode(dotcode, filename):
            self.set_title(os.path.basename(filename) + ' - Dot Viewer')
            self.widget.zoom_to_fit()

    def open_file(self, filename):
        try:
            fp = file(filename, 'rt')
            self.set_dotcode(fp.read(), filename)
            fp.close()
        except IOError:
            # TODO: show an error message
            pass

    def on_open(self, action):
        chooser = gtk.FileChooserDialog(title="Open dot File",
                                        action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                        buttons=(gtk.STOCK_CANCEL,
                                                 gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_OPEN,
                                                 gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        filter = gtk.FileFilter()
        filter.set_name("Graphviz dot files")
        filter.add_pattern("*.dot")
        chooser.add_filter(filter)
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)
        if chooser.run() == gtk.RESPONSE_OK:
            filename = chooser.get_filename()
            chooser.destroy()
            self.open_file(filename)
        else:
            chooser.destroy()


def main():
    import optparse

    parser = optparse.OptionParser(
        usage="\n\t%prog [file]",
        version="%%prog %s" % __version__)

    (options, args) = parser.parse_args(sys.argv[1:])
    if len(args) > 1:
        parser.error('incorrect number of arguments')

    win = DotWindow()
    win.connect('destroy', gtk.main_quit)
    if len(args) >= 1:
        if args[0] == '-':
            win.set_dotcode(sys.stdin.read())
        else:
            win.open_file(args[0])
    gtk.main()


if __name__ == '__main__':
    main()
