import xml.etree.ElementTree as ET
import os
import sys
import re
import datetime
import base64
import hashlib
import binascii
import click
from dateutil.parser import parse


def handle_attachments(text):
    """ Note content may have attachments, such as images.
    <div><en-media hash="..." type="application/pdf" style="cursor:pointer;" /></div>
    <div><en-media hash="..." type="image/png" /><br /></div>
    <div><en-media hash="..." type="image/jpeg" /></div> """
    matched_text = re.sub("<en-media(\s*hash=\"(?P<hashcode>[0-9a-f]+)\"|\s*width=\"(?P<width>\d+?)?p?x?\"|\s*height=\"(?P<height>\d+?)p?x?\"|\s*(width|height)=\"(|[A-Za-z]+|[0-9]+%)\"|\s*(title|style|type|border|alt|vspace|hspace|align)=\"([^\"]*?)\")+\s*(\/>|>.*?<\/en-media>)","ATCHMT:\g<hashcode>:\g<width>:\g<height>:",text)
    return matched_text

def handle_tables(text):
    """ Split by tables. Within the blocks containing tables, remove divs. """

    parts = re.split(r'(<table.*?</table>)', text)

    new_parts = []
    for part in parts:
        if part.startswith('<table'):
            part = part.replace('<div>', '')
            part = part.replace('</div>', '')
        new_parts.append(part)

    text = ''.join(new_parts)

    return text

def handle_strongs_emphases(text):
    """ Make these work.
    <span style="font-weight: bold;">This text is bold.</span>
    <span style="font-style: italic;">This text is italic.</span>
    <span style="font-style: italic; font-weight: bold;">This text is bold and italic.</span>

    <div>
    <span style="font-style: italic; font-weight: bold;"><br /></span>
    </div>
    <div>This text is normal. <i><b>This text is bold and italic.</b></i> This text is normal again.</div>
    """
    parts = re.split(r'(<span.*?</span>)', text)

    new_parts = []
    for part in parts:
        match = re.match(r'<span style=(?P<formatting>.*?)>(?P<content>.*?)</span>', part)
        if match:
            if match.group('content') == '<br />':
                part = '<br />'
            else:
                if 'font-style: italic;' in match.group('formatting') and 'font-weight: bold;' in match.group('formatting'):
                    part = f"<i><b>{match.group('content')}</b></i>"
                    #part = f"<span>***{match.group('content')}***</span>"
                elif 'font-weight: bold;' in match.group('formatting'):
                    part = f"<b>{match.group('content')}</b>"
                    #part = f"<span>**{match.group('content')}**</span>"
                elif 'font-style: italic;' in match.group('formatting'):
                    part = f"<i>{match.group('content')}</i>"
                    #part = f"<span>*{match.group('content')}*</span>"
        new_parts.append(part)

    text = ''.join(new_parts)

    return text

def handle_tasks(text):
    text = text.replace('<en-todo checked="true"/>', '[x] ')
    text = text.replace('<en-todo checked="false"/>', '[ ] ')
    text = text.replace('<en-todo checked="true" />', '[x] ')
    text = text.replace('<en-todo checked="false" />', '[ ] ')
    return text

def make_safe_name(input_string=None, counter=0):
    better = input_string.replace(' ', '_')
    better = "".join([c for c in better if re.match(r'\w', c)])
    if len(better) > 70: # Avoiding far too long filenames
        better = better[:70]
    # For handling duplicates: If counter > 0, append to file/folder name.
    if counter > 0:
        better = f"{better}_{counter}"
    return better

def create_output_folder(input_name):
    ''' See that the folder does not exist. If it doesn't, create it.
        Name is created from a timestamp: 20190202_172208
    '''

    subfolder_name = input_name.replace('\\','/').split('/')[-1]
    #print("SUBFOLDER IS:"+ subfolder_name)
    subfolder_name = make_safe_name(subfolder_name.split('.')[0])

    folder_name = f"output/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}/{subfolder_name}"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    return folder_name

def format_note(note):
    note_content = []
    note_content.append("<html><head>")
    note_content.append(f"<title>{note['title']}</title>")
    if 'author' in note:
        note_content.append(f"<meta name=\"author\" content=\"{note['author']}\">")
    note_content.append(f"<meta name=\"created\" content=\"{note['created']}\">")
    if 'updated' in note:
        note_content.append(f"<meta name=\"updated\" content=\"{note['updated']}\">")
    note_content.append(f"<meta name=\"source\" content=\"Evernote\">")
    if 'source_url' in note:
        note_content.append(f"<meta name=\"source_url\" content=\"{note['source_url']}\">")
    note_content.append(f"<meta name=\"tags\" content=\"{note['tags_string']}\">")
    note_content.append("<style>")
    note_content.append("body { font-family: Arial, sans-serif; }")
    note_content.append("</style>")
    note_content.append("")
    note_content.append("</head><body>")
    note_content.append(f"<h1>{note['title']}</h1>")
    note_content.append(note['content'])
    note_content.append("</body></html>")

    return note_content

def process_enex_file(file_name):
    date_format = '%d.%m.%Y %H:%M:%S'

    # Create an ElementTree object
    tree = ET.iterparse(file_name, events=('start', 'end'))

    # Initialize variables
    all_notes = []
    earlier_filenames = []
    sequence_number = 0
    evernote = {}
    resource = {}
    note_started = False
    resource_started = False
    

    # Iterate over the events in the ElementTree
    for event, element in tree:
        if event == 'start' and element.tag == 'note':
            note_started = True
        elif event == 'end' and element.tag == 'note':
             # When a 'note' element ends, output and save the variables collected!
            #if 'title' in evernote: 
                #print(f"Title: {evernote['title']}")
                #print(f"Created: {evernote['created']}")
            #if evernote['title'].startswith('ASA'):
            #    print(str(evernote))
            # Store this note for later handling
            all_notes.append(evernote)

            # Reset the variables for the next note
            evernote = {}
            resource = {}
            earlier_filenames = []
            sequence_number = 0
            note_started = False
            resource_started = False

        # Get the title when inside a 'note' element
        if note_started and event == 'start':
            if element.tag == 'title':
                evernote['title'] = element.text
                evernote['html_filename_base'] = make_safe_name(element.text)
            elif element.tag == 'created' and element.text is not None:
                evernote['created'] = f"{parse(element.text).strftime(date_format)} GMT"
            elif element.tag == 'updated' and element.text is not None:
                evernote['updated'] = f"{parse(element.text).strftime(date_format)} GMT"
            elif element.tag == 'author':
                evernote['author'] = element.text
            elif element.tag == 'source':
                evernote['source'] = element.text
            elif element.tag == 'source-url':
                evernote['source-url'] = element.text
            elif element.tag == 'tag':
                if 'tags' not in evernote.keys():
                    evernote['tags'] = []
                evernote['tags'].append(element.text)
            elif element.tag == 'content':
                if element.text is None:
                    evernote['content'] = ""
                else:
                    evernote['content'] = element.text
            elif element.tag == 'latitude' :
                evernote['latitude'] = element.text
            elif element.tag == 'longitude' :
                evernote['longitude'] = element.text
            elif element.tag == 'altitude' :
                evernote['altitude'] = element.text
            elif element.tag == 'resource':
                resource_started = True
            elif element.tag == 'mime' and resource_started:
                resource['mime-type'] = element.text
            elif element.tag == 'data' and resource_started:
                if element.text is None:
                    resource['data'] = ""
                else:
                    resource['data'] = element.text
                #print("DATA START TAG!")
            elif element.tag == 'width' and resource_started:
                resource['width'] = element.text
            elif element.tag == 'height' and resource_started:
                resource['height'] = element.text
            elif element.tag == 'file-name' and resource_started:
                resource['file-name'] = element.text

        if note_started and event == 'end' and element.tag == 'content':
            note_content = evernote['content']
            if element.text is not None:
                note_content += element.text
            if 'tags' in evernote.keys():
                evernote['tags_string'] = ", ".join(tag for tag in evernote['tags'])
            else:
                evernote['tags_string'] = ""
            # Clean up the content by removing custom tags
            note_content = re.sub(r'^.*<en-note>(.*)<\/en-note>.*$','\g<1>',note_content, flags=re.DOTALL)
            note_content = handle_attachments(note_content)
            note_content = handle_tasks(note_content)
            #note_content = handle_strongs_emphases(note_content)
            evernote['content'] = note_content

        if note_started and resource_started and event == 'end':
            if element.tag == 'data':
                if element.text is not None:
                    resource['data'] += element.text
            elif element.tag == 'resource':
                if resource['file-name'] is None:
                    if resource['mime-type'] is None:
                        print("RESOURCE WITHOUT NAME AND MIME-TYPE. Assuming jpeg!")
                        print(evernote['title'])
                        resource['mime-type'] = 'image/jpeg'
                    #else:
                        #print("RESOURCE WITHOUT NAME. Mime-type:" + resource['mime-type'])
                    extension = 'txt'
                    if resource['mime-type'].endswith('jpeg'):
                        extension = 'jpg'
                    elif resource['mime-type'].endswith('png'):
                        extension = 'png'
                    elif resource['mime-type'].endswith('gif'):
                        extension = 'gif'
                    resource['file-name'] = 'noname.' + extension
                # Remove unwanted characters
                resource['file-name'] = resource['file-name'].replace(':','_')
                # Make sure resource filename is unique by prefixing it if not unique
                proposed_name = resource['file-name']
                while proposed_name in earlier_filenames:
                    sequence_number += 1
                    proposed_name = str(sequence_number)+"_"+resource['file-name']
                resource['file-name'] = proposed_name
                earlier_filenames.append(resource['file-name'])
                # Handle resource. Base64 encoded data has new lines! Because why not!
                if resource['data'] is None:
                    print("  * * * *   RESOURCE WITH NO DATA  (Will be ignored!)  * * * *")
                else:
                    #print("DATA IS:"+str(resource['data']))
                    clean_data = re.sub(r'\n', '', resource['data']).strip()
                    resource['data'] = clean_data
                    if 'attachments' not in evernote.keys():
                        evernote['attachments'] = []
                    evernote['attachments'].append(resource)
                #Reset for next resource
                resource = {}

        # Clear the element to release memory for large files
        element.clear()

    # Clear the root to release memory for large files
    tree.root.clear()

    return all_notes

def fix_attachment_reference(content, md5_hash, mime_type, dir, name):
    if mime_type.startswith('image/'):
        #content = content.replace(f"ATCHMT:{md5_hash}", f"<img src=\"{dir}/{name}\" alt=\"{name}\">")
        width = 0
        height = 0
        sizematch = re.search(r"ATCHMT\:"+md5_hash+"\:(\d+)\:(\d+)\:", content)
        if sizematch:
            width = int(sizematch.group(1))
            height = int(sizematch.group(2))
        if width == 0 or height == 0 or width>1800:
            content = re.sub(r"ATCHMT\:"+md5_hash+"\:(\d+)\:(\d+)\:", "<img src=\""+dir+"/"+name+"\" alt=\""+name+"\" width=\"100%\">", content)
        else:
            #print("SIZE OK "+str(width))
            content = re.sub(r"ATCHMT\:"+md5_hash+"\:(\d+)\:(\d+)\:", "<img src=\""+dir+"/"+name+"\" alt=\""+name+"\" width=\"\g<1>\" height=\"\g<2>\">", content)
    else:
        # For other than image attachments, we make a link to the document (for now).
        content = re.sub(r"ATCHMT\:"+md5_hash+"\:(\d+)\:(\d+)\:", "<a href=\""+dir+"/"+name+"\">"+name+"</a>", content)
    return content

def write_html(notes, output_folder):
    for note in notes:
        # Check, that the file name does not exist already. If it does, generate a new one.
        filename_base = note['html_filename_base']
        filename = f"{output_folder}/{filename_base}.html"
        counter = 0
        while os.path.exists(filename):
            counter += 1
            filename_base = make_safe_name(note['html_filename_base'], counter)
            filename = f"{output_folder}/{filename_base}.html"

        # Write attachments to disk, and fix references to note content.
        if 'attachments' in note.keys() and note['attachments'] is not None:
            attachment_folder_name = f"{output_folder}/{filename_base}_attachments"
            if not os.path.exists(attachment_folder_name):
                os.makedirs(attachment_folder_name)

            for attachment in note['attachments']:
                try:
                    decoded_attachment = base64.b64decode(attachment['data'])
                    with open(f"{attachment_folder_name}/{attachment['file-name']}", 'wb') as attachment_file:
                        attachment_file.write(decoded_attachment)

                    # Create MD5 hash
                    md5 = hashlib.md5()
                    md5.update(decoded_attachment)
                    md5_hash = binascii.hexlify(md5.digest()).decode()

                    # Fix attachment reference to note content
                    note['content'] = fix_attachment_reference(
                        note['content'],
                        md5_hash,
                        attachment['mime-type'],
                        f"{filename_base}_attachments",
                        attachment['file-name']
                    )
                    if "<en-media" in note['content']:
                        print("Failed to fix en-media in files "+ note['title'])

                except Exception as e:
                    print(f"Error processing attachment on note {filename_base}, attachment: {attachment['file-name']}")
                    print(str(e))

        # Write the actual html note to disk.
        with open(filename, 'w', encoding="utf-8") as output_file:
            formatted_note = format_note(note)
            for line in formatted_note:
                output_file.write(line + "\n")

@click.command()
@click.argument('enex_file')
def app(enex_file):
    """ Run the converter. Requires the enex_file (data.enex) to be processed as the first argument. """
    
    print(f"Processing input file: {enex_file}, writing output to folder 'output'.")

    the_notes = process_enex_file(enex_file)
    output_folder = create_output_folder(enex_file)
    write_html(the_notes, output_folder)

    sys.exit()


if __name__ == '__main__':
    app()

