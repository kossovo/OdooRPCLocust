#!/usr/bin/env python
# -*- coding: utf-8 -*-

from OdooRPCLocust import OdooRPCLocust
from odoo_sabc import SABCTaskSet


class Seller(OdooRPCLocust):
        # Odoo options
        host = "127.0.0.1"
        database = "sabc_locust"
        login = "admin"
        password = "admin"

        # Locust options
        min_wait = 100
        max_wait = 1000
        weight = 3

        tasks = [SABCTaskSet]
