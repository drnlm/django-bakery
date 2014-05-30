import os
import six
import sys
import boto
import time
import hashlib
import mimetypes
from django.conf import settings
from optparse import make_option
from django.core.management.base import BaseCommand, CommandError

# import from cStringIO, if possible
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

# import gzip library, if needed
BAKERY_GZIP = getattr(settings, 'BAKERY_GZIP', False)
if BAKERY_GZIP:
    from gzip import GzipFile

custom_options = (
    make_option(
        "--config",
        action="store",
        dest="config",
        default='',
        help="Specify the path of an s3cmd configuration file. \
Will use ~/.s3cmd by default."
    ),
    make_option(
        "--build-dir",
        action="store",
        dest="build_dir",
        default='',
        help="Specify the path of the build directory. \
Will use settings.BUILD_DIR by default."
    ),
    make_option(
        "--aws-bucket-name",
        action="store",
        dest="aws_bucket_name",
        default='',
        help="Specify the AWS bucket to sync with. \
Will use settings.AWS_BUCKET_NAME by default."
    ),
    make_option(
        "--force",
        action="store_true",
        dest="force",
        default="",
        help="Force a republish of all items in the build directory"
    ),
)

# The list of content types to gzip, add more if needed
# might not need this, instead sticking with the regex, since our files are already gzipped
GZIP_CONTENT_TYPES = (
    'text/css',
    'text/html',
    'application/javascript',
    'application/x-javascript',
    'application/xml'
)
ACL = 'public-read'

def isPythonVersion(version):
    if float(sys.version[:3]) >= version:
        return True
    else:
        return False


class Command(BaseCommand):
    help = "Syncs the build directory with Amazon S3 bucket using s3cmd"
    option_list = BaseCommand.option_list + custom_options
    build_missing_msg = "Build directory does not exist. Cannot publish \
something before you build it."
    build_unconfig_msg = "Build directory unconfigured. Set BUILD_DIR in \
settings.py or provide it with --build-dir"
    bucket_unconfig_msg = "AWS bucket name unconfigured. Set AWS_BUCKET_NAME \
in settings.py or provide it with --aws-bucket-name"

    def gzip_content(self, content):
        """Gzip the contents of a file"""
        zbuf = StringIO()
        if isPythonVersion(2.7):
            zfile = GzipFile('wb', mtime=0, fileobj=zbuf)
        else:
            zfile = GzipFile('wb', fileobj=zbuf)
        zfile.write(content)
        zfile.close()
        return zbuf.getvalue()

    def upload_s3(self, key, filename):
        headers = {}

        # guess and add the mimetype to header
        content_type = mimetypes.guess_type(filename)[0]
        headers['Content-Type'] = content_type

        # add the gzip headers, if necessary
        if content_type in self.gzip_content_types and self.gzip:
            file_obj = open(filename, 'rb')
            file_data = file_obj.read()
            file_data = self.gzip_content(file_data)
            headers['Content-Encoding'] = 'gzip'
            key.set_contents_from_string(file_data, headers, policy=self.acl)
            six.print_('gzipping file %s' % key.name)
            self.uploaded_files += 1
        else:
            # access and write the contents from the file
            with open(filename, 'rb') as file_obj: 
                key.set_contents_from_file(file_obj, headers, policy=self.acl)
                self.uploaded_files += 1

    def sync_s3(self, dirname, names):
        for fname in names:
            filename = os.path.join(dirname, fname)
            
            if os.path.isdir(filename):
                continue # don't try to upload directories

            # get the relative path to the file, which is also the s3 key name
            file_key = os.path.join(os.path.relpath(dirname, self.build_dir), fname)
            if file_key.startswith('./'):
                file_key = file_key[2:]

            # check if the file exists
            if file_key in self.keys:
                key = self.keys[file_key]
                s3_md5 = key.etag.strip('"')
                local_md5 = hashlib.md5(open(filename, "rb").read()).hexdigest()

                # don't upload if the md5 sums are the same
                if s3_md5 == local_md5 and not self.force_publish:
                    pass
                elif self.force_publish:
                    six.print_("forcing update of file %s" % file_key)
                    self.upload_s3(key, filename)                    
                else:
                    six.print_("updating file %s" % file_key)
                    self.upload_s3(key, filename)

                # remove the file from the dict, we don't need it anymore
                del self.keys[file_key]

            # if the file doesn't exist, create it
            else:
                six.print_("creating file %s" % file_key)
                key = self.bucket.new_key(file_key)
                self.upload_s3(key, filename)

    def handle(self, *args, **options):
        """
        Cobble together s3cmd command with all the proper options and run it.
        """
        self.gzip_content_types = GZIP_CONTENT_TYPES
        self.acl = ACL
        self.gzip = BAKERY_GZIP
        self.uploaded_files = 0
        self.deleted_files = 0
        start_time = time.time()

        # If the user specifies a build directory...
        if options.get('build_dir'):
            # ... validate that it is good.
            if not os.path.exists(options.get('build_dir')):
                raise CommandError(self.build_missing_msg)
            # Go ahead and use it
            self.build_dir = options.get("build_dir")
        # If the user does not specify a build dir...
        else:
            # Check if it is set in settings.py
            if not hasattr(settings, 'BUILD_DIR'):
                raise CommandError(self.build_unconfig_msg)
            # Then make sure it actually exists
            if not os.path.exists(settings.BUILD_DIR):
                raise CommandError(self.build_missing_msg)
            # Go ahead and use it
            self.build_dir = settings.BUILD_DIR

        # If the user provides a bucket name, use that.
        if options.get("aws_bucket_name"):
            self.aws_bucket_name = options.get("aws_bucket_name")
        else:
            # Otherwise try to find it the settings
            if not hasattr(settings, 'AWS_BUCKET_NAME'):
                raise CommandError(self.bucket_unconfig_msg)
            self.aws_bucket_name = settings.AWS_BUCKET_NAME

        # If the user sets the --force option
        if options.get('force'):
            self.force_publish = True
        else:
            self.force_publish = False

        # initialize the boto connection, grab the bucket
        # and make a dict out of the results object from bucket.list()
        conn = boto.connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
        self.bucket = conn.get_bucket(self.aws_bucket_name)
        self.keys = dict((key.name, key) for key in self.bucket.list())

        # walk through the build directory
        for (dirpath, dirnames, filenames) in os.walk(self.build_dir):
            self.sync_s3(dirpath, filenames)

        # delete anything that's left in our keys dict
        for key in self.keys:
            six.print_("deleting file %s" % key)
            self.bucket.delete_key(key)
            self.deleted_files += 1

        # we're finished, print the final output
        elapsed_time = time.time() - start_time
        six.print_("publish completed, uploaded %d and deleted %d files in %.2f seconds" % (self.uploaded_files, self.deleted_files, elapsed_time))
