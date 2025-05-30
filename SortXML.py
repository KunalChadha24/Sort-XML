import xml.etree.ElementTree as ET
from collections import OrderedDict
import xml.dom.minidom
import re
import argparse
import os.path
from datetime import datetime

__version__ = "3.0"

# List of keywords that should appear at the top of each element
# This can be configured as needed
priority_keywords = ["id", "keyname", "name", "cfgname", "cfgName", "startup_params", "partition", "mapName", "serverName", "realm_name", "interface_id", "vendorId"]

# Dictionary of priority keywords for specific sub-elements
# Key is the sub-element name, value is a list of priority keywords for that sub-element
# This overrides the general priority_keywords for the specified sub-elements
element_priority_keywords_map = {
    "BdmObject": ["name", "id"], # Contradicting with OvldComponent
    "OvldComponent": ["id", "name"], # Contradicting with BdmObject
    "OvldDropAction": ["type"], # OvldDropAction in ASBC-SIPRE
    "counterPeer": ["appType"], # counterPeer in ASBC-APP
    "TransRouting": ["profileName"], # TransRouting in ASBC-APP and supported vnfType
    "ccsSettings": ["app_type"], # ccsSettings in ASBC-APP
    "domainBasedRealmSetting": ["homeDomain"], # domainBasedRealmSetting in IMC-APP
    "perfMonObjectDef": ["type"],
    #LIXP
    "LiXpErr2CauseCodeConfig": ["error_code"],
    "LiXpTemplateConfig": ["service_name"],

    # Add more sub-element specific priority keywords as needed
    # Example: "SubElementName": ["priority1", "priority2", ...]
}

def xml_to_dict(element):
    """
    Recursively converts an XML element and its children into a Python dictionary.

    If an element has no children, its text content is taken as the value.
    If multiple children have the same tag, their values are aggregated into a list.
    XML namespaces are removed from the tags.

    Args:
        element (xml.etree.ElementTree.Element): The XML element to convert.

    Returns:
        dict or str: A dictionary representing the XML element's structure,
                     or a string if the element has text content but no children.
                     Returns an empty string if the element has no children and no text.
    """
    children = list(element)
    if not children:
        return element.text.strip() if element.text else ''
    result = {}
    for child in children:
        tag = child.tag.split('}')[-1]  # Remove namespace
        value = xml_to_dict(child)
        if tag in result:
            if isinstance(result[tag], list):
                result[tag].append(value)
            else:
                result[tag] = [result[tag], value]
        else:
            result[tag] = value
    return result

def sort_dict(d, parent_tag=None):
    """
    Recursively sorts a dictionary or a list of dictionaries.

    For dictionaries, items are sorted based on a priority key function.
    Keys listed in the global priority_keywords list or in element_priority_keywords_map
    for specific sub-elements are placed first, in the order they appear in the list.
    Remaining keys are sorted alphabetically (case-insensitive).
    If the input is a list, each item in the list is sorted recursively.

    Args:
        d (dict or list): The dictionary or list to be sorted.
        parent_tag (str, optional): The tag name of the parent element. Used to determine
                                    if there are specific priority keywords for this element.

    Returns:
        OrderedDict or list or any:
            - An OrderedDict if the input d is a dictionary, with keys sorted
              according to the priority logic.
            - A list if the input d is a list, with each element recursively sorted.
            - The original item d if it's neither a dictionary nor a list.
    """
    if isinstance(d, dict):
        # First, sort all items case-insensitively by key
        items = []
        for k, v in d.items():
            # Pass the current key as parent_tag for nested dictionaries
            sorted_v = sort_dict(v, k)
            items.append((k, sorted_v))
        items = sorted(items, key=lambda x: x[0].lower())

        # Then, create a custom sorting key function that prioritizes certain keywords
        def priority_key_func(item):
            """
            Generates a sort key for an item (key-value pair).

            Priority is given to keys found in priority_keywords or in element_priority_keywords_map
            for the specific parent_tag.

            Args:
                item (tuple): A (key, value) tuple from the dictionary.

            Returns:
                tuple: A tuple used for sorting. (0, index) for priority keys,
                       (1, key_lower_case) for other keys.
            """
            key_lower = item[0].lower()
            
            # Check if we have specific priority keywords for this parent tag
            if parent_tag and parent_tag in element_priority_keywords_map:
                # Use the specific priority keywords for this parent tag
                specific_priority_keywords = element_priority_keywords_map[parent_tag]
                for i, p_key in enumerate(specific_priority_keywords):
                    if key_lower == p_key.lower():
                        return (0, i)  # Priority items come first, sorted by their order
            else:
                # Use the general priority_keywords
                for i, p_key in enumerate(priority_keywords):
                    if key_lower == p_key.lower():
                        return (0, i)  # Priority items come first, sorted by their order
            
            return (1, key_lower)  # Non-priority items come after, sorted alphabetically

        # Sort again with the priority key function
        return OrderedDict(sorted(items, key=priority_key_func))
    elif isinstance(d, list):
        return [sort_dict(i, parent_tag) for i in d]
    else:
        return d

def dict_to_xml(tag, d, namespace=None):
    """
    Recursively converts a Python dictionary back into an XML element.

    If a value in the dictionary is a list, multiple child elements with the
    same tag are created for each item in the list.
    If a value is not a dictionary or list, its string representation becomes
    the text content of the element.
    A namespace can be added to the created root element.

    Args:
        tag (str): The tag name for the current XML element being created.
        d (dict or any): The dictionary to convert into an XML element. If not a
                         dictionary, its string representation is used as text content.
        namespace (dict, optional): A dictionary defining the namespace attributes
                                    for the element (e.g., {"xmlns": "http://example.com"}).
                                    Defaults to None.

    Returns:
        xml.etree.ElementTree.Element: The constructed XML element.
    """
    if namespace:
        elem = ET.Element(tag, attrib=namespace)
    else:
        elem = ET.Element(tag)
    if isinstance(d, dict):
        for key, val in d.items():
            if isinstance(val, list):
                for item in val:
                    child = dict_to_xml(key, item)
                    elem.append(child)
            else:
                child = dict_to_xml(key, val)
                elem.append(child)
    else:
        elem.text = str(d)
    return elem

def prettify(elem):
    """
    Converts an XML element to a pretty-printed string.

    The output string is indented for readability and the XML declaration
    (e.g., <?xml version="1.0" ?>) is removed.

    Args:
        elem (xml.etree.ElementTree.Element): The XML element to format.

    Returns:
        str: A string containing the pretty-printed XML, without the XML declaration.
    """
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = xml.dom.minidom.parseString(rough_string)
    # Get pretty XML with indentation
    pretty_xml_with_decl = reparsed.toprettyxml(indent="    ")
    # Remove the XML declaration line
    pretty_xml = pretty_xml_with_decl.split('\n', 1)[1] if '<?xml' in pretty_xml_with_decl else pretty_xml_with_decl
    # Ensure double quotes aren't converted to &quot;
    pretty_xml = pretty_xml.replace("&quot;", '"')
    return pretty_xml

def find_cdata_sections(file_path):
    """
    Find all CDATA sections in an XML file.
    
    Args:
        file_path (str): Path to the XML file.
        
    Returns:
        list: A list of tuples containing (element_context, element_tag, cdata_content)
              where element_context is the surrounding XML content that helps identify
              the specific element instance.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find all CDATA sections
    # Look for patterns like <TransRouting>...<profileName>Mav_Trr_Asbc_1</profileName>...<profileXml><![CDATA[...]]></profileXml>
    # We need to capture enough context to uniquely identify each element
    
    # First, find all element blocks that contain CDATA sections
    element_blocks = re.finditer(r'<([^\s>]+)[^>]*>([\s\S]*?)</\1>', content)
    
    cdata_sections = []
    
    for block_match in element_blocks:
        element_tag = block_match.group(1)
        element_content = block_match.group(2)
        
        # Check if this block contains a CDATA section
        cdata_matches = re.finditer(r'<([^>]+)>\s*<!\[CDATA\[(.*?)\]\]>', element_content, re.DOTALL)
        
        for cdata_match in cdata_matches:
            cdata_element_tag = cdata_match.group(1).strip()
            cdata_content = cdata_match.group(2)
            
            # Extract a context signature to uniquely identify this element
            # Look for identifying elements like profileName, id, name, etc.
            context_signature = element_tag  # Start with the parent element tag
            
            # Try to find identifiers in the element content
            identifiers = re.findall(r'<(profileName|name|id|keyname|cfgname|cfgName)>([^<]+)</\1>', element_content)
            if identifiers:
                # Add identifiers to the context signature
                for id_type, id_value in identifiers:
                    context_signature += f":{id_type}={id_value}"
            
            # Create a unique context key for this CDATA section
            element_context = f"{context_signature}:{cdata_element_tag}"
            cdata_sections.append((element_context, cdata_element_tag, cdata_content))
    
    return cdata_sections

def find_xml_declaration_escaped_content(file_path):
    """
    Find all XML elements that contain escaped XML content starting with XML declaration.
    Only detects content that starts with &lt;?xml version="1.0"
    
    Args:
        file_path (str): Path to the XML file.
        
    Returns:
        dict: A dictionary mapping element paths to their escaped XML content.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Dictionary to store elements with escaped XML content
    escaped_xml_elements = {}
    
    # Pattern to find elements with escaped XML declaration
    xml_decl_pattern = re.compile(r'<([^>]+)>([^<>]*?&lt;\?xml version=\"|&lt;\?xml version=\'|&lt;\?xml version=).*?</[^>]*>', re.DOTALL)
    
    for match in xml_decl_pattern.finditer(content):
        element_tag = match.group(1).strip()
        element_content = match.group(2) + match.group(0)[match.start(2) + len(match.group(2)):match.end(0) - len(f'</{element_tag.split()[0]}>')]
        escaped_xml_elements[element_tag] = element_content
    
    return escaped_xml_elements

def find_xml_content_in_elements(file_path, target_elements):
    """
    Find XML content in specific elements, whether in CDATA or escaped format.
    This function is used to identify and preserve XML content in any element,
    not just specific ones like TransRouting or normalizationSettings.
    
    Args:
        file_path (str): Path to the XML file.
        target_elements (list): List of element names to look for.
        
    Returns:
        dict: A dictionary mapping element contexts to their XML content.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    xml_content_map = {}
    
    # Process each target element
    for target_element in target_elements:
        # Find all instances of the target element
        element_pattern = re.compile(f'<{target_element}[^>]*>(.*?)</{target_element}>', re.DOTALL)
        
        for element_match in element_pattern.finditer(content):
            element_content = element_match.group(1)
            
            # Extract identifiers to create a unique context key
            identifiers = re.findall(r'<(profileName|name|id)>([^<]+)</\1>', element_content)
            context_key = target_element
            
            if identifiers:
                for id_type, id_value in identifiers:
                    context_key += f":{id_type}={id_value}"
            
            # Look for XML content in this element (either in CDATA or escaped)
            # First check for CDATA sections
            cdata_matches = re.finditer(r'<([^>]+)>\s*<!\[CDATA\[(.*?)\]\]>', element_content, re.DOTALL)
            
            for cdata_match in cdata_matches:
                xml_tag = cdata_match.group(1).strip()
                xml_content = cdata_match.group(2)
                xml_content_map[f"{context_key}:{xml_tag}"] = ("cdata", xml_content)
            
            # Then check for escaped XML content
            escaped_matches = re.finditer(r'<([^>]+)>([^<]*?&lt;[^>]*?&gt;[^<]*?)</\1>', element_content, re.DOTALL)
            
            for escaped_match in escaped_matches:
                xml_tag = escaped_match.group(1).strip()
                escaped_content = escaped_match.group(2)
                xml_content_map[f"{context_key}:{xml_tag}"] = ("escaped", escaped_content)
    
    return xml_content_map

def process_xml_file(input_file, output_file):
    """
    Processes an XML file by parsing, sorting, and then writing it back.

    The function reads an XML file, converts its content to a dictionary,
    sorts this dictionary (prioritizing certain keys and then alphabetically),
    converts the sorted dictionary back to XML (preserving the original root namespace),
    and writes the "prettified" XML to a specified output file.
    
    CDATA sections are preserved during processing. Additionally, any content with
    escaped XML entities that starts with XML declaration (&lt;?xml version="1.0") 
    is converted to CDATA sections. Any escaped XML entities (&lt;, &gt;, etc.) are
    converted back to proper CDATA format.
    
    Special handling is provided for elements like TransRouting and normalizationSettings
    to ensure their XML content is properly preserved as CDATA.

    Args:
        input_file (str): The path to the input XML file.
        output_file (str): The path where the sorted XML output file will be saved.

    Returns:
        None
        
    Raises:
        ValueError: If the input file appears to be a CDB-backup file (starts with "<config")
    """
    # First, find and store all CDATA sections with their context
    cdata_sections = find_cdata_sections(input_file)
    
    # Find and store all elements with escaped XML content that starts with XML declaration
    escaped_xml_elements = find_xml_declaration_escaped_content(input_file)
    
    # Find all elements with XML content that might need special handling
    # First, get a list of all elements that have CDATA sections
    element_tags_with_cdata = set()
    for element_context, element_tag, _ in cdata_sections:
        parent_tag = element_context.split(':')[0]
        element_tags_with_cdata.add(parent_tag)
    
    # Add known elements that often have XML content
    special_elements = list(element_tags_with_cdata)
    special_elements.extend(["TransRouting", "normalizationSettings"])
    # Remove duplicates
    special_elements = list(set(special_elements))
    
    # Find XML content in all these elements
    xml_content_in_special_elements = find_xml_content_in_elements(input_file, special_elements)
    
    # Read the input file
    with open(input_file, 'r', encoding='utf-8') as f:
        xml_content = f.read()
        
    # Check if this is a CDB-backup file (starts with <config>)
    if xml_content.lstrip().startswith('<config'):
        raise ValueError("This appears to be a CDB-backup file. This tool is not compatible with CDB-backup files. Please use a standard XML file that can be uploaded to CMS.")
    
    # Parse the XML file
    tree = ET.parse(input_file)
    root = tree.getroot()

    # Extract namespace if present
    namespace = None
    namespace_match = re.match(r'\{(.+?)\}', root.tag)
    if namespace_match:
        namespace_uri = namespace_match.group(1)
        namespace = {"xmlns": namespace_uri}

    # Get root tag without namespace
    root_tag = root.tag.split('}')[-1]

    # Convert to dictionary and sort
    xml_dict = {root_tag: xml_to_dict(root)}
    sorted_dict = sort_dict(xml_dict, root_tag)

    # Convert back to XML with namespace preserved
    new_root = dict_to_xml(root_tag, sorted_dict[root_tag], namespace)
    pretty_xml_output = prettify(new_root)
    
    # Restore CDATA sections in the output
    # Group CDATA sections by element tag for easier processing
    cdata_by_tag = {}
    for element_context, element_tag, cdata_content in cdata_sections:
        if element_tag not in cdata_by_tag:
            cdata_by_tag[element_tag] = []
        cdata_by_tag[element_tag].append((element_context, cdata_content))
    
    # Process each element type that has CDATA sections
    for element_tag, context_content_pairs in cdata_by_tag.items():
        # If there's only one CDATA section for this tag, use the simple approach
        if len(context_content_pairs) == 1:
            _, cdata_content = context_content_pairs[0]
            pattern = f'<{element_tag}>([^<]*)</[^>]*>'
            
            def create_cdata_replacement(match):
                return f'<{element_tag}><![CDATA[{cdata_content}]]></{element_tag.split()[0]}>'
            
            pretty_xml_output = re.sub(pattern, create_cdata_replacement, pretty_xml_output)
        else:
            # For multiple CDATA sections with the same tag, we need to match based on context
            for element_context, cdata_content in context_content_pairs:
                # Extract the parent element tag and identifiers
                context_parts = element_context.split(':')
                parent_tag = context_parts[0]
                
                # Build a pattern that includes the context
                if len(context_parts) > 1:
                    # We have identifiers to help match the specific element
                    identifiers = context_parts[1:-1]  # Skip the last part which is the CDATA element tag
                    
                    # Create a pattern to find the specific element instance
                    # This is a complex pattern that tries to match the element with its identifiers
                    parent_pattern = f'<{parent_tag}[^>]*>(.*?)</{parent_tag}>'
                    
                    # Find all instances of the parent element
                    for parent_match in re.finditer(parent_pattern, pretty_xml_output):
                        parent_content = parent_match.group(1)
                        
                        # Check if this parent element contains all the identifiers
                        is_matching_element = True
                        for identifier in identifiers:
                            id_parts = identifier.split('=')
                            if len(id_parts) == 2:
                                id_type, id_value = id_parts
                                # Check if this identifier exists in the parent content
                                if not re.search(f'<{id_type}>{re.escape(id_value)}</{id_type}>', parent_content):
                                    is_matching_element = False
                                    break
                        
                        if is_matching_element:
                            # This is the matching element, replace its CDATA section
                            cdata_pattern = f'<{element_tag}>([^<]*)</[^>]*>'
                            
                            def create_cdata_replacement(match):
                                return f'<{element_tag}><![CDATA[{cdata_content}]]></{element_tag.split()[0]}>'
                            
                            # Replace only within this parent element
                            modified_parent_content = re.sub(cdata_pattern, create_cdata_replacement, parent_content)
                            
                            # Replace the entire parent element in the output
                            pretty_xml_output = pretty_xml_output.replace(
                                f'<{parent_tag}>{parent_content}</{parent_tag}>', 
                                f'<{parent_tag}>{modified_parent_content}</{parent_tag}>'
                            )
                else:
                    # No identifiers, just use the tag
                    pattern = f'<{element_tag}>([^<]*)</[^>]*>'
                    
                    def create_cdata_replacement(match):
                        return f'<{element_tag}><![CDATA[{cdata_content}]]></{element_tag.split()[0]}>'
                    
                    pretty_xml_output = re.sub(pattern, create_cdata_replacement, pretty_xml_output)
    
    # Convert escaped XML content with XML declaration to CDATA sections
    for element_tag, escaped_content in escaped_xml_elements.items():
        # Skip if this element already has a CDATA section
        if element_tag in cdata_by_tag:
            continue
            
        # Create a pattern to find the element in the output
        pattern = f'<{element_tag}>([^<]*)</[^>]*>'
        
        # Function to create replacement with CDATA
        def create_cdata_replacement(match):
            content = match.group(1)
            # Unescape the content if it's escaped
            content = content.replace('&lt;', '<').replace('&gt;', '>')
            content = content.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
            content = content.replace('&quot;', '"').replace('&apos;', "'")
            content = content.replace('&amp;quot;', '"')
            content = content.replace('&amp;', '&')
            # Return the CDATA section with the unescaped content
            return '<' + element_tag + '><![CDATA[' + content + ']]></' + element_tag.split()[0] + '>'
        
        # Replace the content with CDATA section
        pretty_xml_output = re.sub(pattern, create_cdata_replacement, pretty_xml_output)
    
    # Apply special handling for TransRouting and normalizationSettings elements
    for context_key, (content_type, content) in xml_content_in_special_elements.items():
        # Extract the element parts from the context key
        parts = context_key.split(':')
        parent_element = parts[0]  # TransRouting or normalizationSettings
        xml_tag = parts[-1]  # The tag containing XML content (e.g., profileXml)
        
        # Build identifiers to find the specific element instance
        identifiers = []
        for part in parts[1:-1]:  # Skip the first (parent) and last (xml_tag) parts
            if '=' in part:
                identifiers.append(part)
        
        # Create a pattern to find the specific parent element with these identifiers
        parent_pattern = f'<{parent_element}[^>]*>(.*?)</{parent_element}>'        
        
        # Find all instances of the parent element
        for parent_match in re.finditer(parent_pattern, pretty_xml_output):
            parent_content = parent_match.group(1)
            
            # Check if this is the right instance by matching all identifiers
            is_matching_element = True
            for identifier in identifiers:
                id_parts = identifier.split('=')
                if len(id_parts) == 2:
                    id_type, id_value = id_parts
                    # Check if this identifier exists in the parent content
                    if not re.search(f'<{id_type}>{re.escape(id_value)}</{id_type}>', parent_content):
                        is_matching_element = False
                        break
            
            if is_matching_element:
                # This is the matching element, replace its XML content with CDATA
                xml_pattern = f'<{xml_tag}>([^<]*)</{xml_tag}>'                
                
                # Function to create CDATA replacement
                def create_cdata_replacement(match):
                    if content_type == "cdata":
                        # Already CDATA, just use it directly
																	
                        return f'<{xml_tag}><![CDATA[{content}]]></{xml_tag}>'                        
                    else:
                        # Escaped content, unescape it first
                        unescaped = content.replace('&lt;', '<').replace('&gt;', '>')
                        unescaped = unescaped.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
                        unescaped = unescaped.replace('&quot;', '"').replace('&apos;', "'")
                        unescaped = unescaped.replace('&amp;quot;', '"')
                        unescaped = unescaped.replace('&amp;', '&')
														
																	  
                        return f'<{xml_tag}><![CDATA[{unescaped}]]></{xml_tag}>'
                
                # Replace the XML content with CDATA in this parent element
                modified_parent_content = re.sub(xml_pattern, create_cdata_replacement, parent_content)
                
                # Replace the entire parent element in the output
                pretty_xml_output = pretty_xml_output.replace(
                    f'<{parent_element}>{parent_content}</{parent_element}>', 
                    f'<{parent_element}>{modified_parent_content}</{parent_element}>'
                )
    
    # Find and convert any remaining escaped XML entities to CDATA format
    # This handles cases where XML content is escaped but doesn't start with XML declaration
    def convert_escaped_xml_to_cdata(match):
        element_tag = match.group(1)
        content = match.group(2)
        
        # Check if content contains escaped XML entities
        if '&lt;' in content and '&gt;' in content:
            # Unescape the content
            unescaped = content.replace('&lt;', '<').replace('&gt;', '>')
            unescaped = unescaped.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
            unescaped = unescaped.replace('&quot;', '"').replace('&apos;', "'")
            unescaped = unescaped.replace('&amp;quot;', '"')
            unescaped = unescaped.replace('&amp;', '&')
            
            # Only convert to CDATA if it looks like XML content
            if '<' in unescaped and '>' in unescaped and ('</' in unescaped or '/>' in unescaped):
										  
															  
                return f'<{element_tag}><![CDATA[{unescaped}]]></{element_tag.split()[0]}>'
        
        # Return original if no conversion needed
        return match.group(0)
    
    # Apply conversion to all elements with potential escaped XML content
    escaped_xml_pattern = re.compile(r'<([^>]+)>([^<>]*?&lt;[^<>]*?&gt;[^<]*?)</[^>]*>', re.DOTALL)
    pretty_xml_output = re.sub(escaped_xml_pattern, convert_escaped_xml_to_cdata, pretty_xml_output)
    
    with open(output_file, 'w') as f:
        f.write(pretty_xml_output)

if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description=(
            "This script sorts the elements of XML files into a consistent order.\n"
            "Elements are sorted alphabetically, with certain keys prioritized to appear at the top.\n"
            f"These priority keywords are configured in tool: {', '.join(priority_keywords)}.\n"
            "Specific sub-elements can have their own priority keywords defined in element_priority_keywords_map.\n"
            "The script preserves XML namespaces and produces a prettified output.\n\n"
            "You can provide multiple input files separated by spaces."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('input_files', nargs='+', help='Path to one or more input XML files')
    parser.add_argument('-o', '--output', help='Path to the output directory (default: current directory)')
    args = parser.parse_args()

    # Get timestamp for this batch of files
															   
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Process each input file
    for input_file in args.input_files:
        try:
            # Generate output filename by adding "sorted_" prefix and timestamp before the file extension
            input_filename_basename = os.path.basename(input_file)
            
            # Split the filename and extension
            name_parts = os.path.splitext(input_filename_basename)
            base_name = name_parts[0]
            extension = name_parts[1]  # includes the dot
            
            # Create the new filename with timestamp before extension
            output_filename = f"sorted_{base_name}_{timestamp}{extension}"
            
            # If output directory is specified, use it
            if args.output:
                # Create output directory if it doesn't exist
                if not os.path.exists(args.output):
                    os.makedirs(args.output)
                output_filename = os.path.join(args.output, output_filename)

            # Process the XML file
            print(f"📂 Reading input XML file: {input_file}")
            process_xml_file(input_file, output_filename)
            print(f"✅ XML has been sorted successfully based on alphabetical order.")
            print(f"💾 Sorted XML saved as: {output_filename}")
            print("-" * 50)
        except ValueError as e:
            if "CDB-backup file" in str(e):
                print(f"❌ Error processing file {input_file}: {str(e)}")
            else:
                print(f"❌ Error processing file {input_file}: {str(e)}")
            print("-" * 50)
        except Exception as e:
            print(f"❌ Error processing file {input_file}: {str(e)}")
            print("-" * 50)