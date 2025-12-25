#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
import logging 
from src.utils import setup_logging, load_master_excel
from src.web_login import WebLoginAutomation
from src.main import TradingTestSuite

def main():
    setup_logging(level=logging.INFO)
    
    while True:
        print("\n" + "=" * 60)
        print(" ALICEBLUE TRADING SYSTEM - MAIN MENU ".center(60))
        print("=" * 60)
        print("1. 🔐 Web Login All Enabled Accounts")
        print("2. 📊 Run Multi-Account Trading Orders")
        print("3. 🚪 Exit")
        print("=" * 60)
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            print("\n" + "-" * 60)
            print(" INITIATING WEB LOGIN ".center(60))
            print("-" * 60 + "\n")
            
            try:
                login = WebLoginAutomation()
                results = login.login_all_accounts()
                
                if not results:
                    print("\n⚠️ No accounts were processed!")
                    print("   - Check MasterFile.xlsx exists in root folder")
                    print("   - Verify TRADE_ENABLED column has TRUE")
                    print("   - Ensure USERID, Passworrd, Totp are filled")
                else:
                    print("\n📊 Login Summary:")
                    success = sum(1 for v in results.values() if v)
                    for uid, status in results.items():
                        print(f"   {uid}: {'✅ Success' if status else '❌ Failed'}")
                    print(f"\nTotal: {success}/{len(results)} successful")
                
            except Exception as e:
                print(f"\n❌ Error: {e}")
            
            input("\nPress Enter to continue...")
        
        elif choice == '2':
            print("\n" + "-" * 60)
            print(" RUNNING TRADING ORDERS ".center(60))
            print("-" * 60 + "\n")
            
            try:
                suite = TradingTestSuite(config_dir=Path("config"))
                suite.run(multi_account=True)
            except Exception as e:
                print(f"\n❌ Trading error: {e}")
            
            input("\nPress Enter to continue...")
        
        elif choice == '3':
            print("\n👋 Exiting...\n")
            sys.exit(0)
        else:
            print("\n❌ Invalid choice. Try again.")

if __name__ == "__main__":
    main()