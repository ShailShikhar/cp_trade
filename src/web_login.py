#!/usr/bin/env python3
import logging
from pathlib import Path
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyotp

class WebLoginAutomation:
    """Direct wrapper around your Selenium login code"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.master_file = Path("MasterFile.xlsx")
        
    def login_all_accounts(self) -> dict:
        """Execute your login logic and return results"""
        
        if not self.master_file.exists():
            raise FileNotFoundError(f"❌ MasterFile.xlsx not found in: {self.master_file.absolute()}")
        
        print('Please wait! Reading Master excel file...')
        
        # Your exact code starts here
        master_file_path = 'MasterFile.xlsx'
        try:
            Maste_File = pd.read_excel(master_file_path)
            self.logger.info(f"📊 Found {len(Maste_File)} rows in Excel")
        except Exception as e:
            self.logger.error(f"Excel read failed: {e}")
            raise
        
        # Verify required columns exist
        required_cols = ['USER_ID', 'Password', 'Totp']
        missing = [col for col in required_cols if col not in Maste_File.columns]
        if missing:
            raise ValueError(f"❌ Excel missing columns: {missing}. Found: {list(Maste_File.columns)}")
        
        uri = 'https://ant.aliceblueonline.com/'
        results = {}
        
        for index, row in Maste_File.iterrows():
            user_id = str(row.get('USER_ID', '')).strip()
            
            # Skip empty rows
            if pd.isna(row['USER_ID']) or user_id == '':
                self.logger.warning(f"Row {index + 2}: Empty USER_ID, skipping")
                continue
            
            # Check if account is enabled (optional column)
            if 'TRADE_ENABLED' in row:
                is_enabled = str(row['TRADE_ENABLED']).lower() in ['true', '1', 'yes']
                if not is_enabled:
                    self.logger.debug(f"Skipping {user_id}: TRADE_ENABLED=False")
                    continue
            
            print(f'Logging in user: {user_id}')
            
            try:
                # Call your login function
                success = self._do_login(row, uri)
                results[user_id] = success
                print(f"   Result: {'✅ Success' if success else '❌ Failed'}")
            except Exception as e:
                self.logger.error(f"Login failed for {user_id}: {e}")
                results[user_id] = False
        
        return results
    
    def _do_login(self, row, uri: str) -> bool:
        """Your exact Selenium logic wrapped in a function"""
        password = str(row.
Password).strip()
        user_id = str(row.USER_ID).strip()
        secret_key_otp = str(row.Totp).strip()
        
        options = Options()
        options.add_argument('--incognito')
        options.add_argument('--disable-extensions')
        
        driver = webdriver.Chrome(options=options)
        success = False
        
        try:
            driver.get(uri)
            
            # Wait for page load
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            print('document ready')
            print(f"Logging in: {user_id}")
            
            # Enter User ID
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="new_login_userId"]')))
            username_input = driver.find_element(By.XPATH, '//*[@id="new_login_userId"]')
            username_input.clear()
            username_input.send_keys(user_id)
            
            # Enter Password
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="new_login_password"]')))
            password_input = driver.find_element(By.XPATH, '//*[@id="new_login_password"]')
            password_input.clear()
            password_input.send_keys(password)
            
            # Click Next
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="buttonLabel_Next"]')))
            next_button = driver.find_element(By.XPATH, '//*[@id="buttonLabel_Next"]')
            next_button.click()
            
            # Enter OTP
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="new_login_otp"]')))
            otp = pyotp.TOTP(secret_key_otp).now()
            otp_input = driver.find_element(By.XPATH, '//*[@id="new_login_otp"]')
            otp_input.clear()
            otp_input.send_keys(otp)
            
            # Click Next again
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="buttonLabel_Next"]')))
            otp_submit = driver.find_element(By.XPATH, '//*[@id="buttonLabel_Next"]')
            otp_submit.click()
            
            # Click Proceed
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="Proceed_btn"]')))
            proceed_button = driver.find_element(By.XPATH, '//*[@id="Proceed_btn"]')
            proceed_button.click()
            
            # Wait for dashboard
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            success = True
            
        except Exception as e:
            print(f"❌ Error during login: {e}")
            self.logger.error(f"Login sequence error: {e}")
        finally:
            try:
                driver.quit()
            except:
                pass
        
        return success