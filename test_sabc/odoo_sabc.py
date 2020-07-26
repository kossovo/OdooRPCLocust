#!/usr/bin/env python
# -*- coding: utf-8 -*-
import random
import time

from locust import User, task, between, TaskSet


class SABCTaskSet(TaskSet):

    @task(20)
    def make_sale(self):
        """
        1. Les Ventes

        Connexion de l'utilisateur
        navigation vers le menu de ventes
        Création d'un bon de commande
        validation du bon de commande
        Livraison des produits au travers de la validation du bon de livraison
        Création de la facture de vente
        Validation de la facture
        Création d'un avoir de facture pour les emballages
        Ajout du montant de l’avoir à la facture
        Paiement de la facture
        Déconnexion de l'utilisateur

        """
        odoo = self.client

        product = odoo.env['product.product']
        partner = odoo.env['res.partner']
        sorder = odoo.env['sale.order']
        invoice = odoo.env['account.invoice']
        refund = odoo.env['account.invoice.refund']
        picking = odoo.env['stock.picking']

        partner_ids = partner.search([('active', '=', True), ('customer', '=' , True)])
        product_ids = product.search([('sale_ok', '=', True)], limit=80)

        so_id = sorder.create({
            'partner_id': partner_ids[0],
            'order_line': [(0, 0, {'product_id': product_ids[0],
                            'product_uom_qty':1}),
                           (0, 0, {'product_id': product_ids[1],
                            'product_uom_qty':2})],

        })
        # Confirm order
        so = sorder.browse(so_id)
        so.action_confirm()

        # Delivery
        for picking in so.picking_ids:
            picking.action_assign()
            picking.button_validate()

        # Create and validate invoice
        inv_id = so.action_invoice_create()

        inv = invoice.browse(inv_id)
        inv.action_invoice_sent()
        inv.action_invoice_open()

        # Create and account refund for package
        rfd_id = refund.create({
            'description': "Emballage",
            'filter_refund': 'refund',
        })

        rfd = refund.browse(rfd_id)
        rfd.invoice_refund()

        # Paid invoice
        inv.action_invoice_paid()


    wait_time = between(5, 15)


    @task(50)
    def make_sale_by_pos(self):
        """
        Connexion de l'utilisateur
        Navigation vers le menu point de ventes
        Ouverture de la session dans le menu point de vente
        Choix des produit pour la commande
        Effectuer la déconsignation des produits à l'aide de l'interface de déconsignation
        Paiement de la facture
        Fermeture du point de vente
        Fermeture de la session du point de vente
        Passage des écriture en comptabilité
        Déconnexion de l'utilisateur

        """
        odoo = self.client

        taxe_mdl = odoo.env['account.tax']
        pos_mdl = odoo.env['pos.order']
        invoice_mdl = odoo.env['account.invoice']
        sale_mdl = odoo.env['sale.order']
        product_mdl = odoo.env['product.product']
        partner_mdl = odoo.env['res.partner']
        session_mdl = odoo.env['pos.session']
        pos_statement_mdl = odoo.env['pos.open.statement']
        company_mdl = odoo.env['res.company']
        make_payment_mdl = odoo.env['pos.make.payment']
        journal_mdl = odoo.env['account.journal']
        user_mdl = odoo.env['res.users']
        pos_config_mdl = odoo.env['pos.config']

        user_ids = user_mdl.search([('active', '=', True)])
        user_id = random.choice(user_ids)
        user = user_mdl.browse(user_id)

        company = user.company_id
        partner = user.partner_id

        product_ids = product_mdl.search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
            ('company_id', '=', company.id)])
        products = product_mdl.browse(product_ids)

        journal_ids = journal_mdl.search([
            ('type', '=', 'sale'),
            ('company_id', '=', company.id),
            ('active', '=', True)])
        journals = journal_mdl.browse(journal_ids)

        # company = odoo.env.ref('base.main_company')
        default_pos_config = odoo.env.ref('point_of_sale.pos_config_main')
        pos_config_ids = pos_config_mdl.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
            ('journal_id', 'in', journal_ids)], limit=1) or default_pos_config.id
        pos_configs = pos_config_mdl.browse(pos_config_ids)

        # Create a new session
        session_id = session_mdl.create({
            'user_id': user_id,
            'config_id': random.choice(pos_configs).id,
        })
        session = session_mdl.browse(session_id)

        # Open all statements/cash registers
        pos_statement_id = pos_statement_mdl.create({})
        pos_statement = pos_statement_mdl.browse(pos_statement_id)
        pos_statement.open_statement()

        # Create pos order with two lines
        pos_order_id = pos_mdl.create({
            'company_id': company.id,
            'partner_id': partner.id,
            'pricelist_id': partner.property_product_pricelist.id,
            'lines': [(0, 0, {
                'name': "OL/0001",
                'product_id': products[0],
                'price_unit': 450,
                'discount': 5.0,
                'qty': 2.0,
                'tax_ids': [(6, 0, products[0].taxes_id.ids)],
                'price_subtotal': 450 * (1 - 5/100.0) * 2,
                'price_subtotal_incl': 450 * (1 - 5/100.0) * 2,
            }), (0, 0, {
                'name': "OL/0002",
                'product_id': products[1],
                'price_unit': 300,
                'discount': 5.0,
                'qty': 3.0,
                'tax_ids': [(6, 0, products[1].taxes_id.ids)],
                'price_subtotal': 300 * (1 - 5/100.0) * 3,
                'price_subtotal_incl': 300 * (1 - 5/100.0) * 3,
            })],
            'amount_total': 1710.0,
            'amount_tax': 0.0,
            'amount_paid': 1710.0,
            'amount_return': 0.0,
        })

        pos_order = pos_mdl.browse(pos_order_id)

        # Create a refund
        refund_action = pos_order.refund()
        refund = pos_mdl.browse(refund_action['res_id'])

        payment_context = {"active_ids": refund.ids, "active_id": refund.id}
        refund_payment_id = make_payment_mdl.with_context(**payment_context).create({
            'amount': refund.amount_total
        })

        # click on the validate button to register the payment
        refund_payment = make_payment_mdl.browse(refund_payment_id)
        refund_payment.with_context(**payment_context).check()

        # I generate an invoice from the order
        pos_inv = pos_order.action_pos_order_invoice()

        # Create picking
        picking_id = pos_order.create_picking()

        # I create a bank statement with Opening and Closing balance 0.
        account_statement_id = odoo.env['account.bank.statement'].create({
            'balance_start': 0.0,
            'balance_end_real': 0.0,
            'date': time.strftime('%Y-%m-%d'),
            'journal_id': journals[0].id,
            'company_id': company.id,
            'name': 'pos session test',
        })

        # I create bank statement line
        account_statement_line_id = odoo.env['account.bank.statement.line'].create({
            'amount': 1000,
            'partner_id': partner.id,
            'statement_id': account_statement_id,
            'name': 'EXT001'
        })

        # modify the bank statement and set the Closing Balance
        account_statement_mdl.browse(account_statement_id).write({
            'balance_end_real': 1000.0,
        })

        # reconcile the bank statement.
        new_aml_dicts = [{
            'account_id': partner.property_account_receivable_id.id,
            'name': "EXT001",
            'credit': 1000.0,
            'debit': 0.0,
        }]

        odoo.env['account.reconciliation.widget'].process_bank_statement_line(
            account_statement_line.ids, [{'new_aml_dicts': new_aml_dicts}])

        # I confirm the bank statement using Confirm button
        odoo.env['account.bank.statement'].button_confirm_bank()

        # Close de session
        session.action_pos_session_closing_control()


    @task(30)
    def make_stock(self):
        """
        Connexion à l'application
        Navigation vers le menu Inventaire
        Effectuer des transferts de stock
        Effectuer les inventaires de stock
        Déconnexion de l'utilisateur

        """
        odoo = self.client

        product_mdl = odoo.env['product.product']
        partner_mdl = odoo.env['res.partner']
        stock_move_mdl = odoo.env['stock.move']
        stock_move_line_mdl = odoo.env['stock.move.line']
        stock_inventory_mdl = odoo.env['stock.inventory']
        stock_inventory_line_mdl = odoo.env['stock.inventory.line']
        stock_picking_mdl = odoo.env['stock.picking']
        stock_quant_mdl = odoo.env['stock.quant']
        model_data_mdl = odoo.env['ir.model.data']
        uom_mdl = odoo.env['uom.uom']
        stock_location_mdl = odoo.env['stock.location']
        user_mdl = odoo.env['res.users']
        warehouse_mdl = odoo.env['stock.warehouse']

        # Model data
        picking_type_in_id = model_data_mdl.xmlid_to_res_id('stock.picking_type_in')
        picking_type_out_id = model_data_mdl.xmlid_to_res_id('stock.picking_type_out')
        # stock_location_id = model_data_mdl.xmlid_to_res_id('stock.stock_location_stock')
        catef_unit_id = model_data_mdl.xmlid_to_res_id('uom.product_uom_categ_unit')
        supplier_location_id = model_data_mdl.xmlid_to_res_id('stock.stock_location_suppliers')
        customer_location_id = model_data_mdl.xmlid_to_res_id('stock.stock_location_customers')
        uom_unit = odoo.env.ref('uom.product_uom_unit')
        uom_dozen = odoo.env.ref('uom.product_uom_dozen')
        pack_location = odoo.env.ref('stock.location_pack_zone')
        output_location = odoo.env.ref('stock.stock_location_output')
        user_group_stock_manager = odoo.env.ref('stock.group_stock_manager')

        # Search data
        user_ids = user_mdl.search([('active', '=', True)])
        user_id = random.choice(user_ids)
        user = user_mdl.browse(user_id)

        company = user.company_id
        partner = user.partner_id

        warehouse_ids = warehouse_mdl.search([
            ('company_id', '=', company.id), ('active', '=', True)])

        product_ids = product_mdl.search([
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
            ('company_id', '=', company.id)])
        products = product_mdl.browse(product_ids)

        product = random.choice(products)  # Product to used

        # Browse data
        supplier_location = stock_location_mdl.browse(supplier_location_id)
        customer_location = stock_location_mdl.browse(customer_location_id)
        picking_type_in = stock_picking_mdl.browse(picking_type_in_id)

        # Choose a random warehouse and stock location
        warehouses = warehouse_mdl.browse(warehouse_ids)
        warehouse = random.choice(warehouses)
        stock_location = warehouse.lot_stock_id

        # Stock move
        move_id = stock_move_mdl.create({
            'name': 'test_in_1',
            'location_id': supplier_location.id,
            'location_dest_id': stock_location.id,
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': 5.0,
            'picking_type_id': picking_type_in.id,
            'company_id': company.id,
        })

        move = stock_move_mdl.browse(move_id)

        # Confirm stock move
        move._action_confirm()

        # Assignment
        move._action_assign()

        # Fill the move line
        move_line = move.move_line_ids[0]
        move_line.qty_done = 100.0

        # Validate
        move._action_done()

        # INVENTORY
        inventory_wizard_id = odoo.env['stock.change.product.qty'].create({
            'product_id': product.id,
            'new_quantity': 50.0,
            'location_id': random.choice(stock_location).id,
        })

        inventory_wizard = odoo.env['stock.change.product.qty'].browse(inventory_wizard_id)
        inventory_wizard.change_product_qty()

        # Make inventory as sudo to avoid access error
        inventory_id = stock_inventory_mdl.sudo().create({
            'name': 'Starting for product test',
            'filter': 'product',
            'location_id': stock_location.id,
            'product_id': product.id,
        })

        inventory = stock_inventory_mdl.browse(inventory_id)
        inventory.action_start()

        # Update the line, set to 35
        inventory.line_ids.write({'product_qty': 35.0})
        inventory.action_validate()

    @task(1)
    def stop(self):
        self.interrupt()
