import logging
import os

class HELPERS():

    def __init__(self,args):
        self.args = args

    def parse_extra_tags(self,tags_str):
        tags_lst = []
        tags_splt = tags_str.split(';')

        for tag in tags_splt:
            tag_key = tag.split(':')[0]
            tag_val = tag.split(':')[1]
            tag = {
                "Key": tag_key,
                "Value": tag_val
            }
            tags_lst.append(tag)

        return tags_lst

    def write_attribute_to_file(self,path,value):

        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        try:
            f = open(path,"w+")
            f.write(value)
            f.close()
        except Exception as e:
            logging.critical("Error while writing attribute %s to file %s - %s" % (value,path, str(e)))
            raise

