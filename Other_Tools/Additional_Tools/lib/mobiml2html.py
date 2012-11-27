#! /usr/bin/python
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

class Unbuffered:
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
    def __getattr__(self, attr):
        return getattr(self.stream, attr)

import sys
sys.stdout=Unbuffered(sys.stdout)


# Modified version of Calibre Mobi/reader.py
# to remove all code to unpack the mobi file
# and to remove dependencies on lxml, BeautifulSoup , etc

# Original author is  '2008, Kovid Goyal <kovid at kovidgoyal.net>'
# license is GPL v3 based on the original license

# this program works in concert with mobiunpack.py

'''
Convert from Mobi ML to XHTML
'''

import os
import re
import struct

class MobiMLConverter(object):

    PAGE_BREAK_PAT = re.compile(r'(<[/]{0,1}mbp:pagebreak\s*[/]{0,1}>)+', re.IGNORECASE)
    IMAGE_ATTRS = ('lowrecindex', 'recindex', 'hirecindex')

    def __init__(self, filename):
        self.base_css_rules =  'blockquote { margin: 0em 0em 0em 1.25em; text-align: justify }\n'
        self.base_css_rules += 'p { margin: 0em; text-align: justify }\n'
        self.base_css_rules += '.bold { font-weight: bold }\n'
        self.base_css_rules += '.italic { font-style: italic }\n'
        self.base_css_rules += '.mbp_pagebreak { page-break-after: always; margin: 0; display: block }\n'
        self.tag_css_rules = {}
        self.tag_css_rule_cnt = 0
        self.filename = filename
        self.wipml = open(self.filename, 'rb').read()
        self.orig_codec = None
        self.pos = 0
        opfname = self.filename.rsplit('.',1)[0] + '.opf'
        self.opf = open(opfname, 'rb').read()
        self.opos = 0
        self.meta = ''
        self.cssname = os.path.join(os.path.dirname(self.filename),'styles.css')


    # now parse the opf to extract meta information
    def getMetaData(self):
        opftags = {
            'dc:title' : 'Title',
            'dc:creator' : 'Author',
            'dc:publisher' : 'Publisher',
            'dc:rights' : 'Rights',
            'dc:date' : 'Published',
            'dc:language' : 'Language',
            'dc:description' : 'Description',
            'dc:subject' : 'Subject',
        }
        idschemes = {
            'uid' : 'UniqueID',
            'ISBN': 'ISBN',
        }
        metadata = {}
        getfield = False
        content = None
        while True:
            r = self.parseopf()
            if not r:
                break
            text, tag = r
            if text:
                if getfield:
                    content = text
            if tag:
                ttype, tname, tattr = self.parsetag(tag)
                if tattr == None: tattr = {}
                if tname in opftags:
                    if ttype == 'begin':
                        getfield = True
                    else:
                        name = opftags[tname]
                        metadata[name] = content
                        content = None
                        getfield = False
                elif tname == 'dc:identifier':
                    if ttype == 'begin':
                        getfield = True
                    else:
                        scheme = tattr.get('id','uid')
                        name = idschemes.get(scheme,'Identifier')
                        metadata[name] = content
                        content = None
                        getfield = False
                elif tname == 'output':
                    if ttype == 'begin' or ttype == 'single':
                        codec = tattr.get('encoding','Windows-1252')
                        self.orig_codec = codec
                        name = 'Codec'
                        metadata[name] = 'utf-8'

                elif tname == 'meta':
                    if ttype == 'begin' or ttype == 'single':
                        name = tattr.get('name', '')
                        content = tattr.get('content', '')
                        metadata[name] = content


        # store the metadata as html tags
        # Handle Codec and Title and then all of the remainder
        self.meta += '<title>' + metadata.get('Title','Untitled') + '</title>\n'
        self.meta += '<meta http-equiv="content-type" content="text/html; charset=' + metadata.get('Codec','Windows-1252') + '" />\n'
        for key in metadata.keys():
            tag = '<meta name="' + key + '" content="' + metadata[key] + '" />\n'
            self.meta += tag
        if self.orig_codec != 'utf-8':
            meta = self.meta
            meta = meta.decode(self.orig_codec)
            meta = meta.encode('utf-8')
            self.meta = meta


    def cleanup_html(self):
        if self.orig_codec != 'utf-8':
            wipml = self.wipml
            wipml = wipml.decode(self.orig_codec)
            wipml = wipml.encode('utf-8')
            self.wipml = wipml
        self.wipml = re.sub(r'<div height="0(pt|px|ex|em|%){0,1}"></div>', '', self.wipml)
        self.wipml = self.wipml.replace('\r\n', '\n')
        self.wipml = self.wipml.replace('> <', '>\n<')
        self.wipml = self.wipml.replace('<mbp: ', '<mbp:')
        self.wipml = re.sub(r'<?xml[^>]*>', '', self.wipml)
        self.wipml = self.wipml.replace('<br></br>','<br/>')


    def replace_page_breaks(self):
        self.wipml = self.PAGE_BREAK_PAT.sub(
            '<div class="mbp_pagebreak"></div>\n',
            self.wipml)

    # parse leading text of ml and tag
    def parseml(self):
        p = self.pos
        if p >= len(self.wipml):
            return None
        if self.wipml[p] != '<':
            res = self.wipml.find('<',p)
            if res == -1 :
                res = len(self.wipml)
            self.pos = res
            return self.wipml[p:res], None
        tb = p
        te = self.wipml.find('>',p+1)
        ntb = self.wipml.find('<',p+1)
        if ntb != -1 and ntb < te:
            self.pos = ntb
            return self.wipml[p:ntb], None
        self.pos = te + 1
        return None, self.wipml[p:te+1]


    # parse leading text of opf and tag
    def parseopf(self):
        p = self.opos
        if p >= len(self.opf):
            return None
        if self.opf[p] != '<':
            res = self.opf.find('<',p)
            if res == -1 :
                res = len(self.opf)
            self.opos = res
            return self.opf[p:res], None
        tb = p
        te = self.opf.find('>',p+1)
        ntb = self.opf.find('<',p+1)
        if ntb != -1 and ntb < te:
            self.opos = ntb
            return self.opf[p:ntb], None
        self.opos = te + 1
        return None, self.opf[p:te+1]



    # parses string version of tag to identify its name,
    # its type 'begin', 'end' or 'single',
    # plus build a hashtable of its atributes
    # code is written to handle the possiblity of very poor formating
    def parsetag(self, s):
        p = 1
        # get the tag name
        tname = None
        ttype = None
        tattr = None
        while s[p:p+1] == ' ' : p += 1
        if s[p:p+1] == '/':
            ttype = 'end'
            p += 1
            while s[p:p+1] == ' ' : p += 1
        b = p
        while s[p:p+1] not in ('>', '/', ' ', '"') : p += 1
        tname=s[b:p].lower()
        if not ttype:

            # parse any attributes
            tattr = {}
            while s.find('=',p) != -1 :
                while s[p:p+1] == ' ' : p += 1
                b = p
                while s[p:p+1] != '=' : p += 1
                aname = s[b:p].lower()
                aname = aname.rstrip(' ')
                p += 1
                while s[p:p+1] == ' ' : p += 1
                if s[p:p+1] == '"' :
                    p = p + 1
                    b = p
                    while s[p:p+1] != '"': p += 1
                    val = s[b:p]
                    p += 1
                else :
                    b = p
                    while s[p:p+1] not in ('>', '/', ' ') : p += 1
                    val = s[b:p]
                tattr[aname] = val

        if tattr and len(tattr)== 0: tattr = None

        # label beginning and single tags
        if not ttype:
            ttype = 'begin'
            if s.find('/',p) >= 0:
                ttype = 'single'

        return ttype, tname, tattr


    # main routine to convert from mobi markup language to html
    def processml(self):

        # first get the metadata from the opf file
        metadata = self.getMetaData()

        # are these really needed
        html_done = False
        head_done = False
        body_done = False

        skip = False

        htmlstr = ''
        self.replace_page_breaks()
        self.cleanup_html()

        # now parse the cleaned up ml into standard xhtml
        while True:

            r = self.parseml()
            if not r:
                break

            text, tag = r

            if text:
                if not skip:
                    htmlstr += text

            if tag:
                ttype, tname, tattr = self.parsetag(tag)

                if tname in ('guide', 'ncx', 'reference', 'svg:svg','svg:image'):
                    if ttype == 'begin':
                        skip = True
                    else:
                        skip = False
                else:
                    taginfo = (ttype, tname, tattr)
                    htmlstr += self.processtag(taginfo)

                    # handle potential issue of multiple html, head, and body setions
                    if tname == 'html' and ttype == 'begin' and not html_done:
                        htmlstr += '\n'
                        html_done = True

                    if tname == 'head' and ttype == 'begin' and not head_done:
                        htmlstr += '\n'
                        # also add in metadata and style link tags
                        htmlstr += self.meta
                        htmlstr += '<link href="styles.css" rel="stylesheet" type="text/css" />\n'
                        head_done = True

                    if tname == 'body' and ttype == 'begin' and not body_done:
                        htmlstr += '\n'
                        body_done = True


        # handle issue of possiby missing html, head, and body tags
        # I have not seen this but the original did something like this so ...

        if not body_done:
            htmlstr = '<body>\n' + htmlstr + '</body>\n'
        if not head_done:
            headstr = '<head>\n'
            headstr += self.meta
            headstr += '<link href="styles.css" rel="stylesheet" type="text/css" />\n'
            headstr += '</head>\n'
            htmlstr = headstr + htmlstr
        if not html_done:
            htmlstr = '<html>\n' + htmlstr + '</html>\n'

        # finally add DOCTYPE info
        htmlstr = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n' + htmlstr

        # save style sheet
        with open(self.cssname, 'wb') as s:
            s.write(self.base_css_rules)
            for cls, rule in self.tag_css_rules.items():
                s.write('.%s { %s }\n' % (cls, rule))
        s.close()
        return htmlstr


    def ensure_unit(self, raw, unit='px'):
        if re.search(r'\d+$', raw) is not None:
            raw += unit
        return raw


    # flatten possibly modified tag back to string
    def taginfo_tostring(self, taginfo):
        (ttype, tname, tattr) = taginfo
        res = '<'
        if ttype == 'end':
            res += '/' + tname + '>'
            return res
        res += tname
        if tattr:
            for key in tattr.keys():
                res += ' '
                res += key + '="'
                res += tattr[key] + '"'
            res == ' '
        if ttype == 'single':
            res += ' />'
        else :
            res += '>'
        return res


    # routines to convert from mobi ml tags atributes to xhtml attributes and styles
    def processtag(self, taginfo):

        # Converting mobi font sizes to numerics
        size_map = {
            'xx-small': '0.5',
            'x-small': '1',
            'small': '2',
            'medium': '3',
            'large': '4',
            'x-large': '5',
            'xx-large': '6',
            }


        # current tag to work on
        (ttype, tname, tattr) = taginfo
        if not tattr:
            tattr = {}

        styles = []

        # have not seen an example of this yet so keep it here to be safe
        # until this is better understood
        if tname in ('country-region', 'place', 'placetype', 'placename',
                'state', 'city', 'street', 'address', 'content'):
            tname = 'div' if tname == 'content' else 'span'
            for key in tattr.keys():
                tattr.pop(key)


        # handle general case of style, height, width, bgcolor in any tag
        if 'style' in tattr.keys():
            style = tattr.pop('style').strip()
            if style:
                styles.append(style)

        if 'height' in tattr.keys():
            height = tattr.pop('height').strip()
            if height and '<' not in height and '>' not in height and re.search(r'\d+', height):
                if tname in ('table', 'td', 'tr'):
                    pass
                elif tname == 'img':
                    tattr['height'] = height
                else:
                    styles.append('margin-top: %s' % self.ensure_unit(height))

        if 'width' in tattr.keys():
            width = tattr.pop('width').strip()
            if width and re.search(r'\d+', width):
                if tname in ('table', 'td', 'tr'):
                    pass
                elif tname == 'img':
                    tattr['width'] =  width
                else:
                    styles.append('text-indent: %s' % self.ensure_unit(width))
                    if width.startswith('-'):
                        styles.append('margin-left: %s' % self.ensure_unit(width[1:]))

        if 'align' in tattr.keys():
            align = tattr.pop('align').strip()
            # print align
            if align:
                if tname in ('table', 'td', 'tr'):
                    pass
                else:
                    styles.append('text-align: %s' % align)

        if 'bgcolor' in tattr.keys():
            # no proprietary html allowed
            if tname == 'div':
                del tattr['bgcolor']

        # now handle tag specific changes

        # should not need to remap this tag in mobi markup
        # if tname == 'i':
        #     tname = 'span'
        #     tattr['class'] = 'italic'

        # should not need to remap this tag in mobi markup
        # elif tname == 'b':
        #     tname = 'span'
        #     tattr['class'] = 'bold'

        # should not need to remap this tag in mobi markup
        # elif tname == 'pre':


        elif tname == 'font':
            sz = ' '
            if 'size' in tattr.keys():
                sz = tattr['size'].lower()
            try:
                float(sz)
            except ValueError:
                if sz in size_map.keys():
                    tattr['size'] = size_map[sz]

        elif tname == 'img':
            for attr in ('width', 'height'):
                if attr in tattr:
                    val = tattr[attr]
                    if val.lower().endswith('em'):
                        try:
                            nval = float(val[:-2])
                            nval *= 16 * (168.451/72) # Assume this was set using the Kindle profile
                            tattr[attr] = "%dpx"%int(nval)
                        except:
                            del tattr[attr]
                    elif val.lower().endswith('%'):
                        del tattr[attr]

        # convert the anchor tags
        if 'filepos-id' in tattr:
            tattr['id'] = tattr.pop('filepos-id')
            if 'name' in tattr and tattr['name'] != tattr['id']:
                tattr['name'] = tattr['id']

        if 'filepos' in tattr:
            filepos = tattr.pop('filepos')
            try:
                tattr['href'] = "#filepos%d" % int(filepos)
            except ValueError:
                pass

        if styles:
            ncls = None
            rule = '; '.join(styles)
            for sel, srule in self.tag_css_rules.items():
                if srule == rule:
                    ncls = sel
                    break
            if ncls is None:
                self.tag_css_rule_cnt += 1
                ncls = 'rule_%d' % self.tag_css_rule_cnt
                self.tag_css_rules[ncls] = rule
            cls = tattr.get('class', '')
            cls = cls + (' ' if cls else '') + ncls
            tattr['class'] = cls

        # convert updated tag back to string representation
        if len(tattr) == 0: tattr = None
        taginfo = (ttype, tname, tattr)
        return self.taginfo_tostring(taginfo)



def main(argv=sys.argv):
    if len(argv) != 2:
        return 1
    else:
        infile = argv[1]

    try:
        print 'Converting Mobi Markup Language to XHTML'
        mlc = MobiMLConverter(infile)
        print 'Processing ...'
        htmlstr = mlc.processml()
        outname = infile.rsplit('.',1)[0] + '_converted.html'
        file(outname, 'wb').write(htmlstr)
        print 'Completed'
        print 'XHTML version of book can be found at: ' + outname

    except ValueError, e:
        print "Error: %s" % e
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
