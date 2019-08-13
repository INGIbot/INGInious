# -*- coding: utf-8 -*-
#
# This file is part of INGInious. See the LICENSE and the COPYRIGHTS files for
# more information about the licensing of this file.

""" A course class with some modification for users """

import gettext
import copy
import logging

from inginious.common.tags import Tag
from inginious.frontend.accessible_time import AccessibleTime
from inginious.frontend.parsable_text import ParsableText


class WebAppCourse(object):
    """ A course with some modification for users """
    _logger = logging.getLogger("inginious.webapp.courses")

    def gettext(self, language, *args, **kwargs):
        translation = self._translations.get(language, gettext.NullTranslations())
        return translation.gettext(*args, **kwargs)

    def get_id(self):
        """ Return the _id of this course """
        return self._id

    def get_fs(self):
        """ Returns a FileSystemProvider which points to the folder of this course """
        return self._fs

    def get_descriptor(self):
        """ Get (a copy) the description of the course """
        return copy.deepcopy(self._content)

    def __init__(self, courseid, content, filesystem, hook_manager):
        """
        :param courseid: the course id
        :param content_description: a dict with all the infos of this course
        :param filesystem: the task filesystem
        """
        self._id = courseid
        self._content = content
        self._fs = filesystem.from_subfolder(courseid)
        self._hook_manager = hook_manager

        self._translations = {}
        translations_fs = self._fs.from_subfolder("$i18n")
        if translations_fs.exists():
            for f in translations_fs.list(folders=False, files=True, recursive=False):
                lang = f[0:len(f) - 3]
                if translations_fs.exists(lang + ".mo"):
                    try:
                        #TODO temporary workaround to avoid crash while updating translations via webdav
                        self._translations[lang] = gettext.GNUTranslations(translations_fs.get_fd(lang + ".mo"))
                    except Exception as e:
                        self._logger.error(str(e))
                else:
                    self._translations[lang] = gettext.NullTranslations()

        try:
            self._name = self._content['name']
        except:
            raise Exception("Course has an invalid name: " + self.get_id())

        if self._content.get('nofrontend', False):
            raise Exception("That course is not allowed to be displayed directly in the webapp")

        try:
            self._admins = self._content.get('admins', [])
            self._tutors = self._content.get('tutors', [])
            self._description = self._content.get('description', '')
            self._accessible = AccessibleTime(self._content.get("accessible", None))
            self._registration = AccessibleTime(self._content.get("registration", None))
            self._registration_password = self._content.get('registration_password', None)
            self._registration_ac = self._content.get('registration_ac', None)
            if self._registration_ac not in [None, "username", "binding", "email"]:
                raise Exception("Course has an invalid value for registration_ac: " + self.get_id())
            self._registration_ac_list = self._content.get('registration_ac_list', [])
            self._groups_student_choice = self._content.get("groups_student_choice", False)
            self._use_classrooms = self._content.get('use_classrooms', True)
            self._allow_unregister = self._content.get('allow_unregister', True)
            self._allow_preview = self._content.get('allow_preview', False)
            self._is_lti = self._content.get('is_lti', False)
            self._lti_keys = self._content.get('lti_keys', {})
            self._lti_send_back_grade = self._content.get('lti_send_back_grade', False)
            self._tags = {key: Tag(key, tag_dict, self.gettext) for key, tag_dict in self._content.get("tags", {}).items()}
        except:
            raise Exception("Course has an invalid YAML spec: " + self.get_id())

        # Force some parameters if LTI is active
        if self.is_lti():
            self._accessible = AccessibleTime(True)
            self._registration = AccessibleTime(False)
            self._registration_password = None
            self._registration_ac = None
            self._registration_ac_list = []
            self._groups_student_choice = False
            self._use_classrooms = True
            self._allow_unregister = False
        else:
            self._lti_keys = {}
            self._lti_send_back_grade = False

    def get_staff(self):
        """ Returns a list containing the usernames of all the staff users """
        return list(set(self.get_tutors() + self.get_admins()))

    def get_admins(self):
        """ Returns a list containing the usernames of the administrators of this course """
        return self._admins

    def get_tutors(self):
        """ Returns a list containing the usernames of the tutors assigned to this course """
        return self._tutors

    def is_open_to_non_staff(self):
        """ Returns true if the course is accessible by users that are not administrator of this course """
        return self.get_accessibility().is_open()

    def is_registration_possible(self, user_info):
        """ Returns true if users can register for this course """
        return self.get_accessibility().is_open() and self._registration.is_open() and self.is_user_accepted_by_access_control(user_info)

    def is_password_needed_for_registration(self):
        """ Returns true if a password is needed for registration """
        return self._registration_password is not None

    def get_registration_password(self):
        """ Returns the password needed for registration (None if there is no password) """
        return self._registration_password

    def get_accessibility(self, plugin_override=True):
        """ Return the AccessibleTime object associated with the accessibility of this course """
        vals = self._hook_manager.call_hook('course_accessibility', course=self, default=self._accessible)
        return vals[0] if len(vals) and plugin_override else self._accessible

    def get_registration_accessibility(self):
        """ Return the AccessibleTime object associated with the registration """
        return self._registration

    def get_access_control_method(self):
        """ Returns either None, "username", "binding", or "email", depending on the method used to verify that users can register to the course """
        return self._registration_ac

    def get_access_control_list(self):
        """ Returns the list of all users allowed by the AC list """
        return self._registration_ac_list

    def can_students_choose_group(self):
        """ Returns True if the students can choose their groups """
        return self._groups_student_choice

    def use_classrooms(self):
        """ Returns True if classrooms are used """
        return self._use_classrooms

    def is_lti(self):
        """ True if the current course is in LTI mode """
        return self._is_lti

    def lti_keys(self):
        """ {name: key} for the LTI customers """
        return self._lti_keys if self._is_lti else {}

    def lti_send_back_grade(self):
        """ True if the current course should send back grade to the LTI Tool Consumer """
        return self._is_lti and self._lti_send_back_grade

    def is_user_accepted_by_access_control(self, user_info):
        """ Returns True if the user is allowed by the ACL """
        if self.get_access_control_method() is None:
            return True
        elif not user_info:
            return False
        elif self.get_access_control_method() == "username":
            return user_info["username"] in self.get_access_control_list()
        elif self.get_access_control_method() == "email":
            return user_info["email"] in self.get_access_control_list()
        elif self.get_access_control_method() == "binding":
            return set(user_info["bindings"].keys()).intersection(set(self.get_access_control_list()))
        return False

    def allow_preview(self):
        return self._allow_preview

    def allow_unregister(self, plugin_override=True):
        """ Returns True if students can unregister from course """
        vals = self._hook_manager.call_hook('course_allow_unregister', course=self, default=self._allow_unregister)
        return vals[0] if len(vals) and plugin_override else self._allow_unregister

    def get_name(self, language):
        """ Return the name of this course """
        return self.gettext(language, self._name) if self._name else ""

    def get_description(self, language):
        """Returns the course description """
        description = self.gettext(language, self._description) if self._description else ''
        return ParsableText(description, "rst", self._translations.get(language, gettext.NullTranslations()))

    def get_tags(self):
        return self._tags
