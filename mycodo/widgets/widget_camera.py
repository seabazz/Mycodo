# coding=utf-8
#
#  widget_camera.py - Camera dashboard widget
#
#  Copyright (C) 2015-2020 Kyle T. Gabriel <mycodo@kylegabriel.com>
#
#  This file is part of Mycodo
#
#  Mycodo is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mycodo is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mycodo. If not, see <http://www.gnu.org/licenses/>.
#
#  Contact at kylegabriel.com
#
import datetime
import json
import logging
import os

from flask import Response
from flask import flash
from flask_babel import lazy_gettext
from flask_login import current_user

from mycodo.config import CAMERA_INFO
from mycodo.databases.models import Camera
from mycodo.devices.camera import camera_record
from mycodo.mycodo_flask.utils import utils_general
from mycodo.utils.constraints_pass import constraints_pass_positive_value

logger = logging.getLogger(__name__)


def camera_img_acquire(image_type, camera_unique_id, max_age):
    """Capture an image and return the filename."""
    if not current_user.is_authenticated:
        return "You are not logged in and cannot access this endpoint"

    if image_type == 'new':
        tmp_filename = None
    elif image_type == 'tmp':
        tmp_filename = f'{camera_unique_id}_tmp.jpg'
    else:
        return
    path, filename = camera_record('photo', camera_unique_id, tmp_filename=tmp_filename)
    if not path and not filename:
        msg = "Could not acquire image."
        logger.error(msg)
        return msg
    else:
        image_path = os.path.join(path, filename)
        time_max_age = datetime.datetime.now() - datetime.timedelta(seconds=int(max_age))
        timestamp = os.path.getctime(image_path)
        if datetime.datetime.fromtimestamp(timestamp) > time_max_age:
            date_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            return_values = f'["{filename}","{date_time}"]'
        else:
            return_values = '["max_age_exceeded"]'
        return Response(return_values, mimetype='text/json')


def camera_img_latest_timelapse(camera_unique_id, max_age):
    """Capture an image and/or return a filename."""
    if not current_user.is_authenticated:
        return "You are not logged in and cannot access this endpoint"

    camera = Camera.query.filter(
        Camera.unique_id == camera_unique_id).first()

    _, tl_path = utils_general.get_camera_paths(camera)

    timelapse_file_path = os.path.join(tl_path, str(camera.timelapse_last_file))

    if camera.timelapse_last_file is not None and os.path.exists(timelapse_file_path):
        time_max_age = datetime.datetime.now() - datetime.timedelta(seconds=int(max_age))
        if datetime.datetime.fromtimestamp(camera.timelapse_last_ts) > time_max_age:
            ts = datetime.datetime.fromtimestamp(camera.timelapse_last_ts).strftime("%Y-%m-%d %H:%M:%S")
            return_values = f'["{camera.timelapse_last_file}","{ts}"]'
        else:
            return_values = '["max_age_exceeded"]'
    else:
        return_values = '["file_not_found"]'
    return Response(return_values, mimetype='text/json')


def can_stream(custom_options_json):
    custom_options = json.loads(custom_options_json)
    camera = Camera.query.filter(Camera.unique_id == custom_options['camera_id']).first()
    if ((custom_options['camera_image_type'] == 'stream' and
            CAMERA_INFO[camera.library]['capable_stream']) or

            (custom_options['camera_image_type'] in ['new_img', 'tmp_img', 'timelapse'] and
             CAMERA_INFO[camera.library]['capable_image'])):
        return True


def execute_at_creation(error, new_widget, dict_widget):
    try:
        if not can_stream(new_widget.custom_options):
            error.append("This camera type is not capable of streaming")
    except Exception as err:
        error.append("execute_at_creation() error: {}".format(err))
    return error, new_widget


def execute_at_modification(
        mod_widget,
        request_form,
        custom_options_json_presave,
        custom_options_json_postsave):
    allow_saving = True
    page_refresh = True
    error = []

    try:
        if not can_stream(json.dumps(custom_options_json_postsave)):
            allow_saving = False
            error.append("This camera type is not capable of streaming")
    except Exception as err:
        error.append("execute_at_modification() error: {}".format(err))

    for each_error in error:
        flash(each_error, "error")

    return allow_saving, page_refresh, mod_widget, custom_options_json_postsave


WIDGET_INFORMATION = {
    'widget_name_unique': 'widget_camera',
    'widget_name': 'Camera',
    'widget_library': '',
    'no_class': True,

    'message': 'Displays a camera image or stream.',

    'execute_at_creation': execute_at_creation,
    'execute_at_modification': execute_at_modification,

    'widget_width': 7,
    'widget_height': 8,

    'endpoints': [
        # Route URL, route endpoint name, view function, methods
        ("/camera_acquire_image/<image_type>/<camera_unique_id>/<max_age>", "camera_acquire_image", camera_img_acquire, ["GET"]),
        ("/camera_latest_timelapse/<camera_unique_id>/<max_age>", "camera_latest_timelapse", camera_img_latest_timelapse, ["GET"])
    ],

    'custom_options': [
        {
            'id': 'camera_id',
            'type': 'select_device',
            'default_value': '',
            'options_select': [
                'Camera',
            ],
            'name': lazy_gettext('Camera'),
            'phrase': lazy_gettext('Select the camera to display')
        },
        {
            'id': 'camera_image_type',
            'type': 'select',
            'default_value': 'new_img',
            'options_select': [
                ('new_img', lazy_gettext('Acquire Image (and save new file)')),
                ('tmp_img', lazy_gettext('Acquire Image (and erase last file)')),
                ('stream', lazy_gettext('Display Live Video Stream')),
                ('timelapse', lazy_gettext('Display Latest Timelapse Image'))
            ],
            'name': 'Image Display Type',
            'phrase': 'Select how to display the image'
        },
        {
            'id': 'max_age',
            'type': 'integer',
            'default_value': 1200,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Max Age'), lazy_gettext('Seconds')),
            'phrase': 'The maximum age of the camera image'
        },
        {
            'id': 'refresh_seconds',
            'type': 'float',
            'default_value': 30.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': '{} ({})'.format(lazy_gettext("Refresh"), lazy_gettext("Seconds")),
            'phrase': 'The period of time between refreshing the widget'
        },
        {
            'id': 'enable_timestamp',
            'type': 'bool',
            'default_value': False,
            'name': lazy_gettext('Show Timestamp'),
            'phrase': lazy_gettext('Show the timestamp on the widget')
        }
    ],

    'widget_dashboard_head': """<!-- No head content -->""",

    'widget_dashboard_title_bar': """<span style="padding-right: 0.5em; font-size: {{each_widget.font_em_name}}em">{% if widget_options['enable_timestamp'] %}<span id="{{each_widget.id}}-timestamp"></span> {% endif %}{{each_widget.name}}</span>""",

    'widget_dashboard_body': """<a id="{{each_widget.id}}-image-href" href="" target="_blank"><img id="{{each_widget.id}}-image-src" style="height: 100%; width: 100%" src=""></a>""",

    'widget_dashboard_js': """
  // Capture image and update the image
  function get_image_cam(dashboard_id, camera_unique_id, image_type, max_age) {
    let url = '';
    let image_type_str = '';
    if (image_type === 'tmp_img') {
      url = '/camera_acquire_image/tmp/' + camera_unique_id + '/' + max_age;
      image_type_str = 'still'
    } else if (image_type === 'new_img') {
      url = '/camera_acquire_image/new/' + camera_unique_id + '/' + max_age;
      image_type_str = 'still'
    } else if (image_type === 'timelapse') {
      url = '/camera_latest_timelapse/' + camera_unique_id + '/' + max_age;
      image_type_str = 'timelapse'
    }

    $.ajax(url, {
      success: function(data, responseText, jqXHR) {
        if (jqXHR.status === 204) {
          document.getElementById(dashboard_id + "-image-src").src = "/static/img/image_error.png";
          document.getElementById(dashboard_id + "-image-href").href = "/static/img/image_error.png";
        }
        else {
          let timestamp_str = '';
          if (image_type_str === 'still') timestamp_str = 'Still: ';
          else if (image_type_str === 'timelapse') timestamp_str = 'Timelapse: ';

          const filename = data[0];
          if (filename === 'max_age_exceeded') {
            // The image timestamp is older than the maximum allowable age
            document.getElementById(dashboard_id + "-image-src").src = "/static/img/image_max_age.png";
            document.getElementById(dashboard_id + "-image-href").href = "/static/img/image_max_age.png";
            if (document.getElementById(dashboard_id + "-timestamp")) document.getElementById(dashboard_id + "-timestamp").innerHTML = timestamp_str + "Max Age Exceeded";
          } else if (filename === 'file_not_found') {
            // No image was found in the directory
            document.getElementById(dashboard_id + "-image-src").src = "/static/img/image_error.png";
            document.getElementById(dashboard_id + "-image-href").href = "/static/img/image_error.png";
            if (document.getElementById(dashboard_id + "-timestamp")) document.getElementById(dashboard_id + "-timestamp").innerHTML = timestamp_str + "File Not Found";
          } else {
            // The image is available and younger than the max age
            const timestamp = data[1];
            const image_no_cache_timestamp = Date.now();
            document.getElementById(dashboard_id + "-image-src").src = "/camera/" + camera_unique_id + "/" + image_type_str + "/" + filename + "?" + image_no_cache_timestamp;
            document.getElementById(dashboard_id + "-image-href").href = "/camera/" + camera_unique_id + "/" + image_type_str + "/" + filename + "?" + image_no_cache_timestamp;
            if (document.getElementById(dashboard_id + "-timestamp")) document.getElementById(dashboard_id + "-timestamp").innerHTML = timestamp_str + timestamp;
          }
        }
      },
      error: function(jqXHR, textStatus, errorThrown) {
        document.getElementById(dashboard_id + "-image-src").src = "/static/img/image_error.png";
        document.getElementById(dashboard_id + "-image-href").href = "/static/img/image_error.png";
        if (document.getElementById(dashboard_id + "-timestamp")) document.getElementById(dashboard_id + "-timestamp").innerHTML = "Error Getting Image";
      }
    });
  }
    
  // Repeat function for get_image_cam()
  function repeat_get_image_cam(dashboard_id, camera_unique_id, period_sec, image_type, max_age) {
    if (image_type === 'stream') {
      document.getElementById(dashboard_id + "-image-src").src = "/video_feed/" + camera_unique_id;
      if (document.getElementById(dashboard_id + "-timestamp")) document.getElementById(dashboard_id + "-timestamp").innerHTML = 'Live Stream';
    } else {
      get_image_cam(dashboard_id, camera_unique_id, image_type, max_age);
      setInterval(function () {get_image_cam(dashboard_id, camera_unique_id, image_type, max_age)}, period_sec * 1000);
    }
  }
""",

    'widget_dashboard_js_ready': """<!-- No JS ready content -->""",

    'widget_dashboard_js_ready_end': """
$(function() {
  repeat_get_image_cam('{{each_widget.id}}', '{{widget_options['camera_id']}}', {{widget_options['refresh_seconds']}}, '{{widget_options['camera_image_type']}}', {{widget_options['max_age']}});
});
"""
}
