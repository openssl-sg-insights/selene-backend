# Mycroft Server - Backend
# Copyright (C) 2019 Mycroft AI Inc
# SPDX-License-Identifier: 	AGPL-3.0-or-later
#
# This file is part of the Mycroft Server.
#
# The Mycroft Server is free software: you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""Endpoint to generate a pairing code and return it to the device.

The response returned to the device consists of:
    code: A six character string generated from a limited set of characters
        (ACEFHJKLMNPRTUVWXY3479) chosen to be easily distinguished when
        spoken or viewed on a device’s display.

    expiration: An integer representing the number of seconds in a day,
        which is the amount of time until a pairing code expires.

    state: A string generated by the device using uuid4. Used by device to
        identify the pairing session.

    token: A SHA512 hash of a string generated by the API using uuid4.
        Used by the API as a unique identifier for the pairing session.
"""
import hashlib
import json
import random
import uuid
from http import HTTPStatus
from logging import getLogger

from selene.api import PublicEndpoint
from selene.util.cache import DEVICE_PAIRING_CODE_KEY

# Avoid using ambiguous characters in the pairing code, like 0 and O, that
# are hard to distinguish on a device display.
ALLOWED_CHARACTERS = "ACEFHJKLMNPRTUVWXY3479"
ONE_DAY = 86400

_log = getLogger(__package__)


class DeviceCodeEndpoint(PublicEndpoint):
    """Endpoint to generate a pairing code and send it back to the device."""

    def get(self):
        """Return a pairing code to the requesting device.

        The pairing process happens in two steps.  First step generates
        pairing code.  Second step uses the pairing code to activate the device.
        The state parameter is used to make sure that the device that is
        """
        response_data = self._build_response()
        return response_data, HTTPStatus.OK

    def _build_response(self):
        """
        Build the response data to return to the device.

        The pairing code generated may already exist for another device. So,
        continue to generate pairing codes until one that does not already
        exist is created.
        """
        response_data = dict(
            state=self.request.args["state"],
            token=self._generate_token(),
            expiration=ONE_DAY,
        )
        added_to_cache = False
        while not added_to_cache:
            pairing_code = self._generate_pairing_code()
            response_data.update(code=pairing_code)
            added_to_cache = self._add_pairing_code_to_cache(response_data)

        return response_data

    @staticmethod
    def _generate_token():
        """Generate the token used by this API to identify pairing session"""
        sha512 = hashlib.sha512()
        sha512.update(bytes(str(uuid.uuid4()), "utf-8"))

        return sha512.hexdigest()

    @staticmethod
    def _generate_pairing_code():
        """Generate the pairing code that will be spoken by the device."""
        pairing_code = "".join(random.choice(ALLOWED_CHARACTERS) for _ in range(6))
        _log.debug("Generated pairing code {}".format(pairing_code))

        return pairing_code

    def _add_pairing_code_to_cache(self, response_data):
        """Add data necessary to activate the device to cache for retrieval."""
        cache_key = DEVICE_PAIRING_CODE_KEY.format(pairing_code=response_data["code"])
        cache_value = dict(**response_data)
        core_packaging_type = self.request.args.get("packaging")
        if core_packaging_type is not None:
            cache_value.update(packaging_type=core_packaging_type)
        added_to_cache = self.cache.set_if_not_exists_with_expiration(
            cache_key, value=json.dumps(cache_value), expiration=ONE_DAY
        )
        if not added_to_cache:
            log_msg = "Pairing code {pairing_code} exists, generating new code"
            _log.debug(log_msg.format(pairing_code=response_data["pairing_code"]))

        return added_to_cache
