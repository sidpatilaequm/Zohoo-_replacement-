-- MySQL dump 10.13  Distrib 8.0.46, for Linux (aarch64)
--
-- Host: localhost    Database: aequm_billing
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `attribute_values`
--

DROP TABLE IF EXISTS `attribute_values`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `attribute_values` (
  `id` int NOT NULL AUTO_INCREMENT,
  `attribute_id` int NOT NULL,
  `value` varchar(160) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_av` (`attribute_id`,`value`),
  CONSTRAINT `fk_av` FOREIGN KEY (`attribute_id`) REFERENCES `attributes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attribute_values`
--

LOCK TABLES `attribute_values` WRITE;
/*!40000 ALTER TABLE `attribute_values` DISABLE KEYS */;
/*!40000 ALTER TABLE `attribute_values` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `attributes`
--

DROP TABLE IF EXISTS `attributes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `attributes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(30) NOT NULL,
  `name` varchar(120) NOT NULL,
  `attr_type` enum('LIST','MULTI','TEXT','NUM','DATE') NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attributes`
--

LOCK TABLES `attributes` WRITE;
/*!40000 ALTER TABLE `attributes` DISABLE KEYS */;
/*!40000 ALTER TABLE `attributes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `banks`
--

DROP TABLE IF EXISTS `banks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `banks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `short_code` varchar(12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `banks`
--

LOCK TABLES `banks` WRITE;
/*!40000 ALTER TABLE `banks` DISABLE KEYS */;
INSERT INTO `banks` VALUES (1,'State Bank of India','SBI'),(2,'HDFC Bank','HDFC'),(3,'ICICI Bank','ICICI'),(4,'Axis Bank','AXIS'),(5,'Kotak Mahindra Bank','KOTAK'),(6,'Punjab National Bank','PNB'),(7,'Bank of Baroda','BOB'),(8,'Canara Bank','CANARA'),(9,'Union Bank of India','UBI'),(10,'IndusInd Bank','INDUS'),(11,'IDFC First Bank','IDFC'),(12,'Yes Bank','YES'),(13,'Bank of India','BOI'),(14,'Indian Bank','INDIAN'),(15,'Central Bank of India','CBI'),(16,'Federal Bank','FED'),(17,'South Indian Bank','SIB'),(18,'Karnataka Bank','KARB'),(19,'RBL Bank','RBL'),(20,'Bandhan Bank','BANDHAN'),(21,'Other','OTHER');
/*!40000 ALTER TABLE `banks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customer_gstins`
--

DROP TABLE IF EXISTS `customer_gstins`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customer_gstins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `customer_id` int NOT NULL,
  `gstin` char(15) NOT NULL,
  `state_code` char(2) NOT NULL,
  `label` varchar(80) DEFAULT NULL,
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `gstin` (`gstin`),
  KEY `fk_cg` (`customer_id`),
  KEY `fk_cg_s` (`state_code`),
  CONSTRAINT `fk_cg` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_cg_s` FOREIGN KEY (`state_code`) REFERENCES `states` (`code`),
  CONSTRAINT `cg_match` CHECK (((left(`gstin`,2) = `state_code`) and (char_length(`gstin`) = 15)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customer_gstins`
--

LOCK TABLES `customer_gstins` WRITE;
/*!40000 ALTER TABLE `customer_gstins` DISABLE KEYS */;
/*!40000 ALTER TABLE `customer_gstins` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `code` varchar(20) NOT NULL,
  `name` varchar(160) NOT NULL,
  `party_type` enum('B2B','B2C') NOT NULL DEFAULT 'B2B',
  `bill_addr` varchar(255) NOT NULL,
  `bill_city` varchar(80) NOT NULL,
  `bill_state` char(2) NOT NULL,
  `bill_pin` char(6) DEFAULT NULL,
  `ship_same` tinyint(1) NOT NULL DEFAULT '1',
  `ship_addr` varchar(255) DEFAULT NULL,
  `ship_city` varchar(80) DEFAULT NULL,
  `ship_state` char(2) DEFAULT NULL,
  `ship_pin` char(6) DEFAULT NULL,
  `pan` char(10) DEFAULT NULL,
  `msme_registered` tinyint(1) NOT NULL DEFAULT '0',
  `msme_number` varchar(30) DEFAULT NULL,
  `bank_name` varchar(120) DEFAULT NULL,
  `bank_ifsc` char(11) DEFAULT NULL,
  `bank_account` varchar(30) DEFAULT NULL,
  `email` varchar(160) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_c` (`tenant_id`,`code`),
  KEY `fk_c_bs` (`bill_state`),
  KEY `fk_c_ss` (`ship_state`),
  CONSTRAINT `fk_c_bs` FOREIGN KEY (`bill_state`) REFERENCES `states` (`code`),
  CONSTRAINT `fk_c_ss` FOREIGN KEY (`ship_state`) REFERENCES `states` (`code`),
  CONSTRAINT `fk_c_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `c_ship_ok` CHECK (((`ship_same` = true) or ((`ship_addr` is not null) and (`ship_state` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customers`
--

LOCK TABLES `customers` WRITE;
/*!40000 ALTER TABLE `customers` DISABLE KEYS */;
/*!40000 ALTER TABLE `customers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `deliveries`
--

DROP TABLE IF EXISTS `deliveries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deliveries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `doc_date` date NOT NULL,
  `so_id` int NOT NULL,
  `ship_to` varchar(400) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dl` (`tenant_id`,`doc_no`),
  KEY `fk_dl_s` (`so_id`),
  CONSTRAINT `fk_dl_s` FOREIGN KEY (`so_id`) REFERENCES `sales_orders` (`id`),
  CONSTRAINT `fk_dl_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `deliveries`
--

LOCK TABLES `deliveries` WRITE;
/*!40000 ALTER TABLE `deliveries` DISABLE KEYS */;
/*!40000 ALTER TABLE `deliveries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `delivery_lines`
--

DROP TABLE IF EXISTS `delivery_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `delivery_lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `delivery_id` int NOT NULL,
  `material_id` int NOT NULL,
  `batch` varchar(40) DEFAULT NULL,
  `stock_type` enum('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL DEFAULT 'NORMAL',
  `exp_date` date DEFAULT NULL,
  `qty` decimal(14,3) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_dll_d` (`delivery_id`),
  KEY `fk_dll_m` (`material_id`),
  CONSTRAINT `fk_dll_d` FOREIGN KEY (`delivery_id`) REFERENCES `deliveries` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dll_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `dll_pos` CHECK ((`qty` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `delivery_lines`
--

LOCK TABLES `delivery_lines` WRITE;
/*!40000 ALTER TABLE `delivery_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `delivery_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `designations`
--

DROP TABLE IF EXISTS `designations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `designations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(80) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `designations`
--

LOCK TABLES `designations` WRITE;
/*!40000 ALTER TABLE `designations` DISABLE KEYS */;
INSERT INTO `designations` VALUES (8,'Accounts Executive'),(7,'Accounts Manager'),(4,'Chief Executive Officer'),(5,'Chief Financial Officer'),(2,'Director'),(6,'General Manager'),(12,'Logistics Coordinator'),(14,'Other'),(3,'Partner'),(1,'Proprietor'),(9,'Purchase Manager'),(13,'Quality Manager'),(10,'Sales Manager'),(11,'Store Keeper');
/*!40000 ALTER TABLE `designations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `discrepancies`
--

DROP TABLE IF EXISTS `discrepancies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `discrepancies` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `grn_no` varchar(40) NOT NULL,
  `grn_date` date NOT NULL,
  `po_id` int NOT NULL,
  `material_id` int NOT NULL,
  `ordered_qty` decimal(14,3) NOT NULL,
  `received_qty` decimal(14,3) NOT NULL,
  `status` enum('HELD','RELEASED') NOT NULL DEFAULT 'HELD',
  `released_on` date DEFAULT NULL,
  `released_by` varchar(120) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_d_t` (`tenant_id`),
  KEY `fk_d_p` (`po_id`),
  KEY `fk_d_m` (`material_id`),
  CONSTRAINT `fk_d_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_d_p` FOREIGN KEY (`po_id`) REFERENCES `purchase_orders` (`id`),
  CONSTRAINT `fk_d_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `d_diff` CHECK ((`ordered_qty` <> `received_qty`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `discrepancies`
--

LOCK TABLES `discrepancies` WRITE;
/*!40000 ALTER TABLE `discrepancies` DISABLE KEYS */;
/*!40000 ALTER TABLE `discrepancies` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `group_perms`
--

DROP TABLE IF EXISTS `group_perms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `group_perms` (
  `group_id` int NOT NULL,
  `perm` varchar(32) NOT NULL,
  PRIMARY KEY (`group_id`,`perm`),
  CONSTRAINT `fk_gp` FOREIGN KEY (`group_id`) REFERENCES `user_groups` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `group_perms`
--

LOCK TABLES `group_perms` WRITE;
/*!40000 ALTER TABLE `group_perms` DISABLE KEYS */;
INSERT INTO `group_perms` VALUES (1,'attrs'),(1,'crec'),(1,'customers'),(1,'data'),(1,'del'),(1,'disc'),(1,'grn'),(1,'gstr'),(1,'hsn'),(1,'invoice'),(1,'materials'),(1,'org'),(1,'phys'),(1,'po'),(1,'registers'),(1,'reports'),(1,'saved'),(1,'so'),(1,'stock'),(1,'users'),(1,'vendors'),(1,'vinv'),(1,'vpay'),(2,'attrs'),(2,'crec'),(2,'customers'),(2,'data'),(2,'del'),(2,'disc'),(2,'grn'),(2,'gstr'),(2,'hsn'),(2,'invoice'),(2,'materials'),(2,'phys'),(2,'po'),(2,'registers'),(2,'reports'),(2,'saved'),(2,'so'),(2,'stock'),(2,'vendors'),(2,'vinv'),(2,'vpay'),(3,'customers'),(3,'del'),(3,'invoice'),(3,'materials'),(3,'reports'),(3,'saved'),(3,'so'),(3,'stock'),(4,'gstr'),(4,'registers'),(4,'reports'),(4,'saved'),(4,'stock');
/*!40000 ALTER TABLE `group_perms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `gstr3b_uploads`
--

DROP TABLE IF EXISTS `gstr3b_uploads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gstr3b_uploads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `period` varchar(7) NOT NULL,
  `uploaded_by` varchar(120) DEFAULT NULL,
  `out_taxable` decimal(16,2) NOT NULL DEFAULT '0.00',
  `out_igst` decimal(16,2) NOT NULL DEFAULT '0.00',
  `out_cgst` decimal(16,2) NOT NULL DEFAULT '0.00',
  `out_sgst` decimal(16,2) NOT NULL DEFAULT '0.00',
  `itc_igst` decimal(16,2) NOT NULL DEFAULT '0.00',
  `itc_cgst` decimal(16,2) NOT NULL DEFAULT '0.00',
  `itc_sgst` decimal(16,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_g3` (`tenant_id`,`period`),
  CONSTRAINT `fk_gstr3b_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gstr3b_uploads`
--

LOCK TABLES `gstr3b_uploads` WRITE;
/*!40000 ALTER TABLE `gstr3b_uploads` DISABLE KEYS */;
/*!40000 ALTER TABLE `gstr3b_uploads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `hsn_codes`
--

DROP TABLE IF EXISTS `hsn_codes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `hsn_codes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `code` varchar(8) NOT NULL,
  `descr` varchar(200) NOT NULL,
  `kind` enum('HSN','SAC') NOT NULL DEFAULT 'HSN',
  `sgst_pct` decimal(5,2) NOT NULL,
  `cgst_pct` decimal(5,2) NOT NULL,
  `igst_pct` decimal(5,2) NOT NULL,
  `cess_pct` decimal(5,2) NOT NULL DEFAULT '0.00',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_h` (`tenant_id`,`code`),
  CONSTRAINT `fk_hsn_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `hsn_codes`
--

LOCK TABLES `hsn_codes` WRITE;
/*!40000 ALTER TABLE `hsn_codes` DISABLE KEYS */;
/*!40000 ALTER TABLE `hsn_codes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `invoice_lines`
--

DROP TABLE IF EXISTS `invoice_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `invoice_lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `invoice_id` int NOT NULL,
  `line_no` smallint NOT NULL,
  `material_id` int NOT NULL,
  `qty` decimal(14,3) NOT NULL,
  `price` decimal(14,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_il` (`invoice_id`,`line_no`),
  KEY `fk_il_m` (`material_id`),
  CONSTRAINT `fk_il_i` FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_il_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `il_pos` CHECK (((`qty` > 0) and (`price` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `invoice_lines`
--

LOCK TABLES `invoice_lines` WRITE;
/*!40000 ALTER TABLE `invoice_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `invoice_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `invoices`
--

DROP TABLE IF EXISTS `invoices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `invoices` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `doc_type` enum('TAX','PRO') NOT NULL DEFAULT 'TAX',
  `doc_date` date NOT NULL,
  `due_date` date DEFAULT NULL,
  `customer_id` int NOT NULL,
  `gstin` char(15) DEFAULT NULL,
  `pos_state` char(2) NOT NULL,
  `po_no` varchar(60) DEFAULT NULL,
  `po_date` date DEFAULT NULL,
  `reverse_chg` enum('Y','N') NOT NULL DEFAULT 'N',
  `converted_from` varchar(40) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `status` enum('ACTIVE','CANCELLED') NOT NULL DEFAULT 'ACTIVE',
  `cancelled_on` date DEFAULT NULL,
  `cancelled_by` varchar(120) DEFAULT NULL,
  `cancel_reason` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_i` (`tenant_id`,`doc_no`),
  KEY `fk_i_c` (`customer_id`),
  KEY `fk_i_p` (`pos_state`),
  KEY `ix_i_date` (`tenant_id`,`doc_date`),
  CONSTRAINT `fk_i_c` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `fk_i_p` FOREIGN KEY (`pos_state`) REFERENCES `states` (`code`),
  CONSTRAINT `fk_i_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `i_due_order` CHECK (((`due_date` is null) or (`due_date` >= `doc_date`))),
  CONSTRAINT `i_po_order` CHECK (((`po_date` is null) or (`po_date` <= `doc_date`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `invoices`
--

LOCK TABLES `invoices` WRITE;
/*!40000 ALTER TABLE `invoices` DISABLE KEYS */;
/*!40000 ALTER TABLE `invoices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `material_attributes`
--

DROP TABLE IF EXISTS `material_attributes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `material_attributes` (
  `material_id` int NOT NULL,
  `attribute_id` int NOT NULL,
  `value` varchar(400) NOT NULL,
  PRIMARY KEY (`material_id`,`attribute_id`),
  KEY `fk_ma_a` (`attribute_id`),
  CONSTRAINT `fk_ma_a` FOREIGN KEY (`attribute_id`) REFERENCES `attributes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ma_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `material_attributes`
--

LOCK TABLES `material_attributes` WRITE;
/*!40000 ALTER TABLE `material_attributes` DISABLE KEYS */;
/*!40000 ALTER TABLE `material_attributes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `materials`
--

DROP TABLE IF EXISTS `materials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `materials` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `code` varchar(30) NOT NULL,
  `descr` varchar(200) NOT NULL,
  `price` decimal(14,2) NOT NULL,
  `cost` decimal(14,2) NOT NULL DEFAULT '0.00',
  `hsn` varchar(8) NOT NULL,
  `stock_qty` decimal(14,3) NOT NULL DEFAULT '0.000',
  `uom` varchar(6) NOT NULL,
  `batch_managed` tinyint(1) NOT NULL DEFAULT '0',
  `shelf_life_days` int NOT NULL DEFAULT '0',
  `sgst_pct` decimal(5,2) NOT NULL,
  `cgst_pct` decimal(5,2) NOT NULL,
  `igst_pct` decimal(5,2) NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_m` (`tenant_id`,`code`),
  KEY `fk_m_uom` (`uom`),
  CONSTRAINT `fk_m_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_m_uom` FOREIGN KEY (`uom`) REFERENCES `uoms` (`code`),
  CONSTRAINT `m_pos` CHECK (((`price` >= 0) and (`cost` >= 0))),
  CONSTRAINT `m_shelf` CHECK ((`shelf_life_days` >= 0)),
  CONSTRAINT `m_split` CHECK ((abs(((`sgst_pct` + `cgst_pct`) - `igst_pct`)) < 0.005))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `materials`
--

LOCK TABLES `materials` WRITE;
/*!40000 ALTER TABLE `materials` DISABLE KEYS */;
/*!40000 ALTER TABLE `materials` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `party_contacts`
--

DROP TABLE IF EXISTS `party_contacts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `party_contacts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `party_kind` enum('CUSTOMER','VENDOR') NOT NULL,
  `party_id` int NOT NULL,
  `first_name` varchar(60) NOT NULL,
  `middle_name` varchar(60) DEFAULT NULL,
  `last_name` varchar(60) DEFAULT NULL,
  `designation_id` int DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `email` varchar(160) DEFAULT NULL,
  `is_primary` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `fk_party_contact_tenant` (`tenant_id`),
  KEY `fk_party_contact_designation` (`designation_id`),
  CONSTRAINT `fk_party_contact_designation` FOREIGN KEY (`designation_id`) REFERENCES `designations` (`id`),
  CONSTRAINT `fk_party_contact_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `party_contacts`
--

LOCK TABLES `party_contacts` WRITE;
/*!40000 ALTER TABLE `party_contacts` DISABLE KEYS */;
/*!40000 ALTER TABLE `party_contacts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payments`
--

DROP TABLE IF EXISTS `payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `pay_type` enum('REC','PAY') NOT NULL,
  `pay_date` date NOT NULL,
  `invoice_id` int DEFAULT NULL,
  `vinv_id` int DEFAULT NULL,
  `amount` decimal(14,2) NOT NULL,
  `tds` decimal(14,2) NOT NULL DEFAULT '0.00',
  `mode` enum('NEFT','RTGS','IMPS','UPI','Cheque','Cash','Adjustment') NOT NULL,
  `bank_ref` varchar(60) DEFAULT NULL,
  `bank_acct` varchar(80) DEFAULT NULL,
  `narration` varchar(200) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `reverses_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_p_t` (`tenant_id`),
  KEY `ix_p_inv` (`invoice_id`),
  KEY `ix_p_vinv` (`vinv_id`),
  CONSTRAINT `fk_p_i` FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_p_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_p_vi` FOREIGN KEY (`vinv_id`) REFERENCES `vendor_invoices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `p_pos` CHECK (((`amount` > 0) and (`tds` >= 0))),
  CONSTRAINT `p_side` CHECK ((((`pay_type` = _utf8mb4'REC') and (`invoice_id` is not null) and (`vinv_id` is null)) or ((`pay_type` = _utf8mb4'PAY') and (`vinv_id` is not null) and (`invoice_id` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payments`
--

LOCK TABLES `payments` WRITE;
/*!40000 ALTER TABLE `payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `physical_counts`
--

DROP TABLE IF EXISTS `physical_counts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `physical_counts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `count_date` date NOT NULL,
  `counted_by` varchar(120) DEFAULT NULL,
  `reason` varchar(200) DEFAULT NULL,
  `material_id` int NOT NULL,
  `batch` varchar(40) DEFAULT NULL,
  `stock_type` enum('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL,
  `book_qty` decimal(14,3) NOT NULL,
  `counted_qty` decimal(14,3) NOT NULL,
  `diff_qty` decimal(14,3) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_pc_t` (`tenant_id`),
  KEY `fk_pc_m` (`material_id`),
  CONSTRAINT `fk_pc_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_pc_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `pc_diff` CHECK (((`diff_qty` = (`counted_qty` - `book_qty`)) and (`diff_qty` <> 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `physical_counts`
--

LOCK TABLES `physical_counts` WRITE;
/*!40000 ALTER TABLE `physical_counts` DISABLE KEYS */;
/*!40000 ALTER TABLE `physical_counts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `po_lines`
--

DROP TABLE IF EXISTS `po_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `po_lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `po_id` int NOT NULL,
  `line_no` smallint NOT NULL,
  `material_id` int NOT NULL,
  `qty` decimal(14,3) NOT NULL,
  `price` decimal(14,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_pl` (`po_id`,`line_no`),
  KEY `fk_pl_m` (`material_id`),
  CONSTRAINT `fk_pl_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_pl_p` FOREIGN KEY (`po_id`) REFERENCES `purchase_orders` (`id`) ON DELETE CASCADE,
  CONSTRAINT `pl_pos` CHECK (((`qty` > 0) and (`price` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `po_lines`
--

LOCK TABLES `po_lines` WRITE;
/*!40000 ALTER TABLE `po_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `po_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `purchase_orders`
--

DROP TABLE IF EXISTS `purchase_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `purchase_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `doc_date` date NOT NULL,
  `req_date` date DEFAULT NULL,
  `vendor_id` int NOT NULL,
  `gstin` char(15) DEFAULT NULL,
  `bill_addr` text NOT NULL,
  `ship_same` tinyint(1) NOT NULL DEFAULT '1',
  `ship_addr` text NOT NULL,
  `status` enum('OPEN','INVOICED','CANCELLED') NOT NULL DEFAULT 'OPEN',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_po` (`tenant_id`,`doc_no`),
  KEY `fk_po_v` (`vendor_id`),
  CONSTRAINT `fk_po_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_po_v` FOREIGN KEY (`vendor_id`) REFERENCES `vendors` (`id`),
  CONSTRAINT `po_req` CHECK (((`req_date` is null) or (`req_date` >= `doc_date`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `purchase_orders`
--

LOCK TABLES `purchase_orders` WRITE;
/*!40000 ALTER TABLE `purchase_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `purchase_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sales_orders`
--

DROP TABLE IF EXISTS `sales_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sales_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `doc_date` date NOT NULL,
  `req_date` date DEFAULT NULL,
  `customer_id` int NOT NULL,
  `cust_ref` varchar(60) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_so` (`tenant_id`,`doc_no`),
  KEY `fk_so_c` (`customer_id`),
  CONSTRAINT `fk_so_c` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `fk_so_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `so_req` CHECK (((`req_date` is null) or (`req_date` >= `doc_date`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sales_orders`
--

LOCK TABLES `sales_orders` WRITE;
/*!40000 ALTER TABLE `sales_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `sales_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `so_lines`
--

DROP TABLE IF EXISTS `so_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `so_lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `so_id` int NOT NULL,
  `line_no` smallint NOT NULL,
  `material_id` int NOT NULL,
  `qty` decimal(14,3) NOT NULL,
  `price` decimal(14,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sol` (`so_id`,`line_no`),
  KEY `fk_sol_m` (`material_id`),
  CONSTRAINT `fk_sol_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_sol_s` FOREIGN KEY (`so_id`) REFERENCES `sales_orders` (`id`) ON DELETE CASCADE,
  CONSTRAINT `sol_pos` CHECK (((`qty` > 0) and (`price` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `so_lines`
--

LOCK TABLES `so_lines` WRITE;
/*!40000 ALTER TABLE `so_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `so_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `states`
--

DROP TABLE IF EXISTS `states`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `states` (
  `code` char(2) NOT NULL,
  `name` varchar(60) NOT NULL,
  PRIMARY KEY (`code`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `states`
--

LOCK TABLES `states` WRITE;
/*!40000 ALTER TABLE `states` DISABLE KEYS */;
INSERT INTO `states` VALUES ('37','Andhra Pradesh'),('18','Assam'),('10','Bihar'),('04','Chandigarh'),('22','Chhattisgarh'),('07','Delhi'),('30','Goa'),('24','Gujarat'),('06','Haryana'),('02','Himachal Pradesh'),('01','Jammu and Kashmir'),('20','Jharkhand'),('29','Karnataka'),('32','Kerala'),('23','Madhya Pradesh'),('27','Maharashtra'),('21','Odisha'),('34','Puducherry'),('03','Punjab'),('08','Rajasthan'),('33','Tamil Nadu'),('36','Telangana'),('09','Uttar Pradesh'),('05','Uttarakhand'),('19','West Bengal');
/*!40000 ALTER TABLE `states` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_ledger`
--

DROP TABLE IF EXISTS `stock_ledger`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stock_ledger` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `move_date` date NOT NULL,
  `source` enum('GRN','GI','PI') NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `material_id` int NOT NULL,
  `stock_type` enum('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL DEFAULT 'NORMAL',
  `batch` varchar(40) DEFAULT NULL,
  `mfg_date` date DEFAULT NULL,
  `exp_date` date DEFAULT NULL,
  `qty` decimal(14,3) NOT NULL,
  `po_id` int DEFAULT NULL,
  `so_id` int DEFAULT NULL,
  `party` varchar(160) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_sl_m` (`material_id`),
  KEY `ix_sl_mat` (`tenant_id`,`material_id`,`batch`,`stock_type`),
  KEY `ix_sl_date` (`tenant_id`,`move_date`),
  CONSTRAINT `fk_sl_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_sl_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `sl_exp` CHECK (((`exp_date` is null) or (`mfg_date` is null) or (`exp_date` >= `mfg_date`))),
  CONSTRAINT `sl_qty` CHECK ((`qty` <> 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_ledger`
--

LOCK TABLES `stock_ledger` WRITE;
/*!40000 ALTER TABLE `stock_ledger` DISABLE KEYS */;
/*!40000 ALTER TABLE `stock_ledger` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tenants`
--

DROP TABLE IF EXISTS `tenants`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tenants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(160) NOT NULL,
  `gstin` char(15) DEFAULT NULL,
  `pan` char(10) DEFAULT NULL,
  `addr` varchar(255) DEFAULT NULL,
  `city` varchar(80) DEFAULT NULL,
  `state_code` char(2) NOT NULL,
  `pin` char(6) DEFAULT NULL,
  `company_type` enum('TRADING','NONTRADING') NOT NULL DEFAULT 'NONTRADING',
  `logo` mediumtext,
  `inv_prefix` varchar(24) NOT NULL DEFAULT 'INV/',
  `inv_seq` int NOT NULL DEFAULT '1',
  `po_prefix` varchar(24) NOT NULL DEFAULT 'PO/',
  `po_seq` int NOT NULL DEFAULT '1',
  `bank` varchar(255) DEFAULT NULL,
  `smtp_from_name` varchar(120) DEFAULT NULL,
  `smtp_from_email` varchar(160) DEFAULT NULL,
  `smtp_reply_to` varchar(160) DEFAULT NULL,
  `smtp_bcc` varchar(160) DEFAULT NULL,
  `smtp_host` varchar(160) DEFAULT NULL,
  `smtp_port` smallint unsigned DEFAULT NULL,
  `smtp_encryption` enum('STARTTLS','SSL','NONE') DEFAULT NULL,
  `smtp_username` varchar(160) DEFAULT NULL,
  `smtp_password` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `gstin` (`gstin`),
  KEY `fk_t_state` (`state_code`),
  CONSTRAINT `fk_t_state` FOREIGN KEY (`state_code`) REFERENCES `states` (`code`),
  CONSTRAINT `t_gstin_st` CHECK (((`gstin` is null) or (left(`gstin`,2) = `state_code`)))
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tenants`
--

LOCK TABLES `tenants` WRITE;
/*!40000 ALTER TABLE `tenants` DISABLE KEYS */;
INSERT INTO `tenants` VALUES (1,'Tour Package','09BBAPS4309G1ZO','BBAPS4309G',NULL,NULL,'09',NULL,'NONTRADING',NULL,'INV/',1,'PO/',1,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2026-09-09 10:44:07');
/*!40000 ALTER TABLE `tenants` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `uoms`
--

DROP TABLE IF EXISTS `uoms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `uoms` (
  `code` varchar(6) NOT NULL,
  `name` varchar(40) NOT NULL,
  PRIMARY KEY (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `uoms`
--

LOCK TABLES `uoms` WRITE;
/*!40000 ALTER TABLE `uoms` DISABLE KEYS */;
INSERT INTO `uoms` VALUES ('BOX','Box'),('EA','Each'),('HRS','Hours'),('KGS','Kilograms'),('LIC','Licence'),('LTR','Litres'),('MTH','Month'),('MTR','Metres'),('NOS','Numbers'),('OTH','Other'),('PAC','Packet'),('SET','Set'),('USR','User');
/*!40000 ALTER TABLE `uoms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_groups`
--

DROP TABLE IF EXISTS `user_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_groups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `name` varchar(80) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_g` (`tenant_id`,`name`),
  CONSTRAINT `fk_g_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_groups`
--

LOCK TABLES `user_groups` WRITE;
/*!40000 ALTER TABLE `user_groups` DISABLE KEYS */;
INSERT INTO `user_groups` VALUES (2,1,'Accounts'),(1,1,'Administrator'),(4,1,'Read only'),(3,1,'Sales');
/*!40000 ALTER TABLE `user_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `user_id` int NOT NULL,
  `tenant_id` int NOT NULL,
  `group_id` int NOT NULL,
  PRIMARY KEY (`user_id`,`tenant_id`),
  KEY `fk_ur_t` (`tenant_id`),
  KEY `fk_ur_g` (`group_id`),
  CONSTRAINT `fk_ur_g` FOREIGN KEY (`group_id`) REFERENCES `user_groups` (`id`),
  CONSTRAINT `fk_ur_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ur_u` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
INSERT INTO `user_roles` VALUES (1,1,1);
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `email` varchar(160) NOT NULL,
  `pwd_hash` varchar(255) NOT NULL,
  `status` enum('ACTIVE','PENDING','DISABLED') NOT NULL DEFAULT 'PENDING',
  `requested_tenant` int DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  KEY `fk_u_req` (`requested_tenant`),
  CONSTRAINT `fk_u_req` FOREIGN KEY (`requested_tenant`) REFERENCES `tenants` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'Prasoon Srivastava','prasoon@tourpartner.in','pbkdf2_sha256$240000$r8ST82Ce8BlFMkv63rb7Vg==$JHCucdOobf0Dr3S0iGbiBEEIMx1+imOtYNb8/KipV74=','ACTIVE',NULL,'2026-09-09 10:44:07');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Temporary view structure for view `v_stock_on_hand`
--

DROP TABLE IF EXISTS `v_stock_on_hand`;
/*!50001 DROP VIEW IF EXISTS `v_stock_on_hand`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_stock_on_hand` AS SELECT 
 1 AS `tenant_id`,
 1 AS `material_id`,
 1 AS `batch`,
 1 AS `stock_type`,
 1 AS `exp_date`,
 1 AS `qty`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `vendor_gstins`
--

DROP TABLE IF EXISTS `vendor_gstins`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendor_gstins` (
  `id` int NOT NULL AUTO_INCREMENT,
  `vendor_id` int NOT NULL,
  `gstin` char(15) NOT NULL,
  `state_code` char(2) NOT NULL,
  `label` varchar(80) DEFAULT NULL,
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `gstin` (`gstin`),
  KEY `fk_vg` (`vendor_id`),
  KEY `fk_vg_s` (`state_code`),
  CONSTRAINT `fk_vg` FOREIGN KEY (`vendor_id`) REFERENCES `vendors` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_vg_s` FOREIGN KEY (`state_code`) REFERENCES `states` (`code`),
  CONSTRAINT `vg_match` CHECK (((left(`gstin`,2) = `state_code`) and (char_length(`gstin`) = 15)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendor_gstins`
--

LOCK TABLES `vendor_gstins` WRITE;
/*!40000 ALTER TABLE `vendor_gstins` DISABLE KEYS */;
/*!40000 ALTER TABLE `vendor_gstins` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vendor_invoice_lines`
--

DROP TABLE IF EXISTS `vendor_invoice_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendor_invoice_lines` (
  `id` int NOT NULL AUTO_INCREMENT,
  `vinv_id` int NOT NULL,
  `line_no` smallint NOT NULL,
  `material_id` int NOT NULL,
  `qty` decimal(14,3) NOT NULL,
  `price` decimal(14,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_vil` (`vinv_id`,`line_no`),
  KEY `fk_vil_m` (`material_id`),
  CONSTRAINT `fk_vil_m` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `fk_vil_v` FOREIGN KEY (`vinv_id`) REFERENCES `vendor_invoices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `vil_pos` CHECK (((`qty` > 0) and (`price` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendor_invoice_lines`
--

LOCK TABLES `vendor_invoice_lines` WRITE;
/*!40000 ALTER TABLE `vendor_invoice_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `vendor_invoice_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vendor_invoices`
--

DROP TABLE IF EXISTS `vendor_invoices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendor_invoices` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `doc_no` varchar(40) NOT NULL,
  `doc_date` date NOT NULL,
  `due_date` date DEFAULT NULL,
  `vendor_id` int NOT NULL,
  `gstin` char(15) DEFAULT NULL,
  `po_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_vi` (`tenant_id`,`vendor_id`,`doc_no`),
  KEY `fk_vi_v` (`vendor_id`),
  KEY `fk_vi_p` (`po_id`),
  CONSTRAINT `fk_vi_p` FOREIGN KEY (`po_id`) REFERENCES `purchase_orders` (`id`),
  CONSTRAINT `fk_vi_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_vi_v` FOREIGN KEY (`vendor_id`) REFERENCES `vendors` (`id`),
  CONSTRAINT `vi_due` CHECK (((`due_date` is null) or (`due_date` >= `doc_date`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendor_invoices`
--

LOCK TABLES `vendor_invoices` WRITE;
/*!40000 ALTER TABLE `vendor_invoices` DISABLE KEYS */;
/*!40000 ALTER TABLE `vendor_invoices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vendors`
--

DROP TABLE IF EXISTS `vendors`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendors` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tenant_id` int NOT NULL,
  `code` varchar(20) NOT NULL,
  `name` varchar(160) NOT NULL,
  `party_type` enum('B2B','B2C') NOT NULL DEFAULT 'B2B',
  `addr` varchar(255) NOT NULL,
  `city` varchar(80) NOT NULL,
  `state_code` char(2) NOT NULL,
  `pin` char(6) DEFAULT NULL,
  `pan` varchar(10) DEFAULT NULL,
  `msme_registered` tinyint(1) NOT NULL DEFAULT '0',
  `msme_number` varchar(30) DEFAULT NULL,
  `bank_name` varchar(120) DEFAULT NULL,
  `bank_ifsc` varchar(11) DEFAULT NULL,
  `bank_account` varchar(24) DEFAULT NULL,
  `email` varchar(160) DEFAULT NULL,
  `tds_section` varchar(10) DEFAULT NULL,
  `tds_rate` decimal(5,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_v` (`tenant_id`,`code`),
  KEY `fk_v_s` (`state_code`),
  CONSTRAINT `fk_v_s` FOREIGN KEY (`state_code`) REFERENCES `states` (`code`),
  CONSTRAINT `fk_v_t` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendors`
--

LOCK TABLES `vendors` WRITE;
/*!40000 ALTER TABLE `vendors` DISABLE KEYS */;
/*!40000 ALTER TABLE `vendors` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'aequm_billing'
--

--
-- Final view structure for view `v_stock_on_hand`
--

/*!50001 DROP VIEW IF EXISTS `v_stock_on_hand`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = latin1 */;
/*!50001 SET character_set_results     = latin1 */;
/*!50001 SET collation_connection      = latin1_swedish_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_stock_on_hand` AS select `stock_ledger`.`tenant_id` AS `tenant_id`,`stock_ledger`.`material_id` AS `material_id`,coalesce(`stock_ledger`.`batch`,'') AS `batch`,`stock_ledger`.`stock_type` AS `stock_type`,max(`stock_ledger`.`exp_date`) AS `exp_date`,sum(`stock_ledger`.`qty`) AS `qty` from `stock_ledger` group by `stock_ledger`.`tenant_id`,`stock_ledger`.`material_id`,coalesce(`stock_ledger`.`batch`,''),`stock_ledger`.`stock_type` having (sum(`stock_ledger`.`qty`) <> 0) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-10 12:05:59
