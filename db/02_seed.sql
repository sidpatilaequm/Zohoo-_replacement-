USE aequm_billing;

INSERT INTO states (code,name) VALUES
('01','Jammu and Kashmir'),('02','Himachal Pradesh'),('03','Punjab'),('04','Chandigarh'),
('05','Uttarakhand'),('06','Haryana'),('07','Delhi'),('08','Rajasthan'),('09','Uttar Pradesh'),
('10','Bihar'),('18','Assam'),('19','West Bengal'),('20','Jharkhand'),('21','Odisha'),
('22','Chhattisgarh'),('23','Madhya Pradesh'),('24','Gujarat'),('27','Maharashtra'),
('29','Karnataka'),('30','Goa'),('32','Kerala'),('33','Tamil Nadu'),('34','Puducherry'),
('36','Telangana'),('37','Andhra Pradesh');

INSERT INTO uoms (code,name) VALUES
('NOS','Numbers'),('EA','Each'),('USR','User'),('LIC','Licence'),('MTH','Month'),
('HRS','Hours'),('KGS','Kilograms'),('LTR','Litres'),('MTR','Metres'),('BOX','Box'),
('SET','Set'),('PAC','Packet'),('OTH','Other');

INSERT INTO designations (name) VALUES
('Proprietor'),('Director'),('Partner'),('Chief Executive Officer'),
('Chief Financial Officer'),('General Manager'),('Accounts Manager'),
('Accounts Executive'),('Purchase Manager'),('Sales Manager'),
('Store Keeper'),('Logistics Coordinator'),('Quality Manager'),('Other');

INSERT INTO banks (name, short_code) VALUES
('State Bank of India','SBI'),('HDFC Bank','HDFC'),('ICICI Bank','ICICI'),
('Axis Bank','AXIS'),('Kotak Mahindra Bank','KOTAK'),('Punjab National Bank','PNB'),
('Bank of Baroda','BOB'),('Canara Bank','CANARA'),('Union Bank of India','UBI'),
('IndusInd Bank','INDUS'),('IDFC First Bank','IDFC'),('Yes Bank','YES'),
('Bank of India','BOI'),('Indian Bank','INDIAN'),('Central Bank of India','CBI'),
('Federal Bank','FED'),('South Indian Bank','SIB'),('Karnataka Bank','KARB'),
('RBL Bank','RBL'),('Bandhan Bank','BANDHAN'),('Other','OTHER');

-- Reference data only. Create the first organisation and its administrator
-- through the sign-up screen, so the password is hashed properly. HSN and SAC
-- codes are per organisation, so they are added from the Masters screen.
