from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from aiohttp import ClientResponseError, ClientSession, ClientTimeout, BasicAuth
from aiohttp_socks import ProxyConnector
from fake_useragent import FakeUserAgent
from datetime import datetime
from base64 import b64encode
import asyncio, random, time, json, re, os, pytz

wib = pytz.timezone('Asia/Jakarta')

PUBLIC_KEY_PEM = b"""
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDWPv2qP8+xLABhn3F/U/hp76HP
e8dD7kvPUh70TC14kfvwlLpCTHhYf2/6qulU1aLWpzCz3PJr69qonyqocx8QlThq
5Hik6H/5fmzHsjFvoPeGN5QRwYsVUH07MbP7MNbJH5M2zD5Z1WEp9AHJklITbS1z
h23cf2WfZ0vwDYzZ8QIDAQAB
-----END PUBLIC KEY-----
"""

class AutoStaking:
    def __init__(self) -> None:
        self.HEADERS = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://autostaking.pro",
            "Referer": "https://autostaking.pro/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": FakeUserAgent().random
        }
        self.BASE_API = "https://api.autostaking.pro"
        self.RPC_URL = "https://testnet.dplabs-internal.com/"
        self.USDC_CONTRACT_ADDRESS = "0x72df0bcd7276f2dFbAc900D1CE63c272C4BCcCED"
        self.USDT_CONTRACT_ADDRESS = "0xD4071393f8716661958F766DF660033b3d35fD29"
        self.MUSD_CONTRACT_ADDRESS = "0x7F5e05460F927Ee351005534423917976F92495e"
        self.mvMUSD_CONTRACT_ADDRESS = "0xF1CF5D79bE4682D50f7A60A047eACa9bD351fF8e"
        self.STAKING_ROUTER_ADDRESS = "0x11cD3700B310339003641Fdce57c1f9BD21aE015"
        self.ERC20_CONTRACT_ABI = json.loads('''[
            {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"address","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
            {"type":"function","name":"allowance","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
            {"type":"function","name":"approve","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}]},
            {"type":"function","name":"decimals","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint8"}]},
            {"type":"function","name":"claimFaucet","stateMutability":"nonpayable","inputs":[],"outputs":[{"name":"","type":"uint256"}]}
        ]''')
        self.AUTOSTAKING_CONTRACT_ABI = [
            {
                "type": "function",
                "name": "getNextFaucetClaimTime",
                "stateMutability": "view",
                "inputs": [
                    { "name": "user", "type": "address" }
                ],
                "outputs": [
                    { "name": "", "type": "uint256" }
                ]
            }
        ]
        self.PROMPTS = [
            # Original balanced strategy
            "1. Mandatory Requirement: The product's TVL must be higher than one million USD.\n"
            "2. Balance Preference: Prioritize products that have a good balance of high current APY and high TVL.\n"
            "3. Portfolio Allocation: Select the 3 products with the best combined ranking in terms of current APY and TVL among those with TVL > 1,000,000 USD. "
            "To determine the combined ranking, rank all eligible products by current APY (highest to lowest) and by TVL (highest to lowest), "
            "then sum the two ranks for each product. Choose the 3 products with the smallest sum of ranks. Allocate the investment equally among these 3 products, "
            "with each receiving approximately 33.3% of the investment.",

            # Alternative 1: Focus on high APY with stability
            "1. Mandatory Requirement: TVL must exceed $1M USD and APY must be at least 5%.\n"
            "2. Priority: Select products with consistently high APY over the last 30 days.\n"
            "3. Allocation: Choose the top 3 performing products meeting criteria. Distribute funds equally (33.3% each).",

            # Alternative 2: Risk-adjusted returns
            "1. Requirement: Minimum TVL of $1.5M USD.\n"
            "2. Strategy: Prioritize products with the best risk-adjusted returns (APY/TVL ratio).\n"
            "3. Diversification: Select 4 products across different protocol categories. Allocate 25% to each.",

            # Alternative 3: Conservative approach
            "1. Requirement: TVL > $2M USD and established protocol (age > 6 months).\n"
            "2. Focus: Capital preservation with moderate returns (APY 5-15%).\n"
            "3. Allocation: Choose 2 products with highest TVL and 1 with best APY stability. Distribute 40%/40%/20%.",

            # Alternative 4: Aggressive growth
            "1. Requirement: TVL > $750K USD with APY > 20%.\n"
            "2. Focus: Maximize short-term returns with higher risk tolerance.\n"
            "3. Allocation: Select 5 highest APY products. Distribute equally (20% each).",

            # Alternative 5: Balanced multi-strategy
            "1. Requirement: TVL > $1.2M USD and positive 90-day performance.\n"
            "2. Strategy: 50% allocation to top 2 TVL products, 30% to top APY, 20% to best risk-adjusted.\n"
            "3. Diversification: Minimum 3 different protocol types. Rebalance monthly."
        ]
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}
        self.auth_tokens = {}
        self.used_nonce = {}
        self.staking_count = 0
        self.usdc_amount = 0
        self.usdt_amount = 0
        self.musd_amount = 0
        self.min_delay = 0
        self.max_delay = 0

    def get_random_prompt(self):
        return random.choice(self.PROMPTS)

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(
            f"\033[36m\033[1m[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]\033[0m"
            f"\033[97m\033[1m | \033[0m{message}",
            flush=True
        )

    def welcome(self):
        print(
            f"""
        \033[92m\033[1mAutoStaking\033[94m\033[1m Auto BOT
            """
            f"""
        \033[92m\033[1mRey? \033[93m\033[1m<INI WATERMARK>
            \033[0m"""
        )

    def format_seconds(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    
    async def load_proxies(self, use_proxy_choice: bool):
        filename = "proxy.txt"
        try:
            if use_proxy_choice == 1:
                async with ClientSession(timeout=ClientTimeout(total=30)) as session:
                    async with session.get("https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt") as response:
                        response.raise_for_status()
                        content = await response.text()
                        with open(filename, 'w') as f:
                            f.write(content)
                        self.proxies = [line.strip() for line in content.splitlines() if line.strip()]
            else:
                if not os.path.exists(filename):
                    self.log(f"\033[91m\033[1mFile {filename} Not Found.\033[0m")
                    return
                with open(filename, 'r') as f:
                    self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]
            
            if not self.proxies:
                self.log("\033[91m\033[1mNo Proxies Found.\033[0m")
                return

            self.log(
                f"\033[92m\033[1mProxies Total  : \033[0m"
                f"\033[97m\033[1m{len(self.proxies)}\033[0m"
            )
        
        except Exception as e:
            self.log(f"\033[91m\033[1mFailed To Load Proxies: {e}\033[0m")
            self.proxies = []

    def check_proxy_schemes(self, proxies):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        if any(proxies.startswith(scheme) for scheme in schemes):
            return proxies
        return f"http://{proxies}"

    def get_next_proxy_for_account(self, token):
        if token not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[token] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[token]

    def rotate_proxy_for_account(self, token):
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[token] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy
    
    def build_proxy_config(self, proxy=None):
        if not proxy:
            return None, None, None

        if proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
            return connector, None, None

        elif proxy.startswith("http"):
            match = re.match(r"http://(.*?):(.*?)@(.*)", proxy)
            if match:
                username, password, host_port = match.groups()
                clean_url = f"http://{host_port}"
                auth = BasicAuth(username, password)
                return None, clean_url, auth
            else:
                return None, proxy, None

        raise Exception("Unsupported Proxy Type.")
    
    def generate_address(self, account: str):
        try:
            account = Account.from_key(account)
            address = account.address
            return address
        except Exception as e:
            return None
        
    def mask_account(self, account):
        try:
            mask_account = account[:6] + '*' * 6 + account[-6:]
            return mask_account
        except Exception as e:
            return None
        
    def generate_auth_token(self, address: str):
        try:
            public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)

            ciphertext = public_key.encrypt(
                address.encode('utf-8'),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            token_base64 = b64encode(ciphertext).decode('utf-8')
            return token_base64
        except Exception as e:
            return None
        
    def generate_recommendation_payload(self, address: str):
        try:
            usdc_assets = int(self.usdc_amount * (10 ** 6))
            usdt_assets = int(self.usdt_amount * (10 ** 6))
            musd_assets = int(self.musd_amount * (10 ** 6))

            payload = {
                "user":address,
                "profile":self.get_random_prompt(),
                "userPositions":[],
                "userAssets":[
                    {
                        "chain":{"id":688688},
                        "name":"USDC",
                        "symbol":"USDC",
                        "decimals":6,
                        "address":"0x72df0bcd7276f2dFbAc900D1CE63c272C4BCcCED",
                        "assets":str(usdc_assets),
                        "price":1,
                        "assetsUsd":self.usdc_amount
                    },
                    {
                        "chain":{"id":688688},
                        "name":"USDT",
                        "symbol":"USDT",
                        "decimals":6,
                        "address":"0xD4071393f8716661958F766DF660033b3d35fD29",
                        "assets":str(usdt_assets),
                        "price":1,
                        "assetsUsd":self.usdt_amount
                    },
                    {
                        "chain":{"id":688688},
                        "name":"MockUSD",
                        "symbol":"MockUSD",
                        "decimals":6,
                        "address":"0x7F5e05460F927Ee351005534423917976F92495e",
                        "assets":str(musd_assets),
                        "price":1,
                        "assetsUsd":self.musd_amount
                    }
                ],
                "chainIds":[688688],
                "tokens":["USDC","USDT","MockUSD"],
                "protocols":["MockVault"],
                "env":"pharos"
            }

            return payload
        except Exception as e:
            raise Exception(f"Generate Req Payload Failed: {str(e)}")
        
    def generate_transactions_payload(self, address: str, change_tx: list):
        try:
            payload = {
                "user":address,
                "changes":change_tx,
                "prevTransactionResults":{}
            }

            return payload
        except Exception as e:
            raise Exception(f"Generate Req Payload Failed: {str(e)}")
        
    async def get_web3_with_check(self, address: str, use_proxy: bool, retries=3, timeout=60):
        request_kwargs = {"timeout": timeout}

        proxy = self.get_next_proxy_for_account(address) if use_proxy else None

        if use_proxy and proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        for attempt in range(retries):
            try:
                web3 = Web3(Web3.HTTPProvider(self.RPC_URL, request_kwargs=request_kwargs))
                web3.eth.get_block_number()
                return web3
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(3)
                    continue
                raise Exception(f"Failed to Connect to RPC: {str(e)}")
            
    async def get_token_balance(self, address: str, contract_address: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)

            token_contract = web3.eth.contract(address=web3.to_checksum_address(contract_address), abi=self.ERC20_CONTRACT_ABI)
            balance = token_contract.functions.balanceOf(address).call()
            decimals = token_contract.functions.decimals().call()

            token_balance = balance / (10 ** decimals)

            return token_balance
        except Exception as e:
            self.log(
                f"\033[36m\033[1m     Message :\033[0m"
                f"\033[91m\033[1m {str(e)} \033[0m"
            )
            return None
        
    async def send_raw_transaction_with_retries(self, account, web3, tx, retries=5):
        for attempt in range(retries):
            try:
                signed_tx = web3.eth.account.sign_transaction(tx, account)
                raw_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                tx_hash = web3.to_hex(raw_tx)
                return tx_hash
            except TransactionNotFound:
                pass
            except Exception as e:
                self.log(
                    f"\033[36m\033[1m    Message :\033[0m"
                    f"\033[93m\033[1m [Attempt {attempt + 1}] Send TX Error: {str(e)} \033[0m"
                )
            await asyncio.sleep(2 ** attempt)
        raise Exception("Transaction Hash Not Found After Maximum Retries")

    async def wait_for_receipt_with_retries(self, web3, tx_hash, retries=5):
        for attempt in range(retries):
            try:
                receipt = await asyncio.to_thread(web3.eth.wait_for_transaction_receipt, tx_hash, timeout=300)
                return receipt
            except TransactionNotFound:
                pass
            except Exception as e:
                self.log(
                    f"\033[36m\033[1m    Message :\033[0m"
                    f"\033[93m\033[1m [Attempt {attempt + 1}] Wait for Receipt Error: {str(e)} \033[0m"
                )
            await asyncio.sleep(2 ** attempt)
        raise Exception("Transaction Receipt Not Found After Maximum Retries")
    
    async def get_next_faucet_claim_time(self, address: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)

            contract_address = web3.to_checksum_address(self.mvMUSD_CONTRACT_ADDRESS)
            token_contract = web3.eth.contract(address=contract_address, abi=self.AUTOSTAKING_CONTRACT_ABI)

            next_faucet_claim_time = token_contract.functions.getNextFaucetClaimTime(web3.to_checksum_address(address)).call()

            return next_faucet_claim_time
        except Exception as e:
            self.log(
                f"\033[36m\033[1m    Message :\033[0m"
                f"\033[91m\033[1m {str(e)} \033[0m"
            )
            return None
        
    async def perform_claim_faucet(self, account: str, address: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)

            contract_address = web3.to_checksum_address(self.mvMUSD_CONTRACT_ADDRESS)
            token_contract = web3.eth.contract(address=contract_address, abi=self.ERC20_CONTRACT_ABI)

            claim_data = token_contract.functions.claimFaucet()
            estimated_gas = claim_data.estimate_gas({"from": address})

            max_priority_fee = web3.to_wei(1, "gwei")
            max_fee = max_priority_fee

            claim_tx = claim_data.build_transaction({
                "from": web3.to_checksum_address(address),
                "gas": int(estimated_gas * 1.2),
                "maxFeePerGas": int(max_fee),
                "maxPriorityFeePerGas": int(max_priority_fee),
                "nonce": self.used_nonce[address],
                "chainId": web3.eth.chain_id,
            })

            tx_hash = await self.send_raw_transaction_with_retries(account, web3, claim_tx)
            receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)

            block_number = receipt.blockNumber
            self.used_nonce[address] += 1

            return tx_hash, block_number
        except Exception as e:
            self.log(
                f"\033[36m\033[1m    Message :\033[0m"
                f"\033[91m\033[1m {str(e)} \033[0m"
            )
            return None, None
        
    async def approving_token(self, account: str, address: str, router_address: str, asset_address: str, amount: float, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)
            
            spender = web3.to_checksum_address(router_address)
            token_contract = web3.eth.contract(address=web3.to_checksum_address(asset_address), abi=self.ERC20_CONTRACT_ABI)
            decimals = token_contract.functions.decimals().call()
            
            amount_to_wei = int(amount * (10 ** decimals))

            allowance = token_contract.functions.allowance(address, spender).call()
            if allowance < amount_to_wei:
                approve_data = token_contract.functions.approve(spender, 2**256 - 1)
                estimated_gas = approve_data.estimate_gas({"from": address})

                max_priority_fee = web3.to_wei(1, "gwei")
                max_fee = max_priority_fee

                approve_tx = approve_data.build_transaction({
                    "from": address,
                    "gas": int(estimated_gas * 1.2),
                    "maxFeePerGas": int(max_fee),
                    "maxPriorityFeePerGas": int(max_priority_fee),
                    "nonce": self.used_nonce[address],
                    "chainId": web3.eth.chain_id,
                })

                tx_hash = await self.send_raw_transaction_with_retries(account, web3, approve_tx)
                receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)

                block_number = receipt.blockNumber
                self.used_nonce[address] += 1

                explorer = f"https://testnet.pharosscan.xyz/tx/{tx_hash}"
                
                self.log(
                    f"\033[36m\033[1m   Approve :\033[0m"
                    f"\033[92m\033[1m Success \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m   Block   :\033[0m"
                    f"\033[97m\033[1m {block_number} \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m   Tx Hash :\033[0m"
                    f"\033[97m\033[1m {tx_hash} \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m   Explorer:\033[0m"
                    f"\033[97m\033[1m {explorer} \033[0m"
                )
                await asyncio.sleep(5)

            return True
        except Exception as e:
            raise Exception(f"Approving Token Contract Failed: {str(e)}")
        
    async def perform_staking(self, account: str, address: str, change_tx: list, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, use_proxy)

            await self.approving_token(account, address, self.STAKING_ROUTER_ADDRESS, self.USDC_CONTRACT_ADDRESS, self.usdc_amount, use_proxy)
            await self.approving_token(account, address, self.STAKING_ROUTER_ADDRESS, self.USDT_CONTRACT_ADDRESS, self.usdt_amount, use_proxy)
            await self.approving_token(account, address, self.STAKING_ROUTER_ADDRESS, self.MUSD_CONTRACT_ADDRESS, self.musd_amount, use_proxy)

            transactions = await self.generate_change_transactions(address, change_tx, use_proxy)
            if not transactions:
                raise Exception("Generate Transaction Calldata Failed")
            
            calldata = transactions["data"]["688688"]["data"]

            estimated_gas = web3.eth.estimate_gas({
                "from": web3.to_checksum_address(address),
                "to": web3.to_checksum_address(self.STAKING_ROUTER_ADDRESS),
                "data": calldata,
            })

            max_priority_fee = web3.to_wei(1, "gwei")
            max_fee = max_priority_fee

            tx = {
                "from": web3.to_checksum_address(address),
                "to": web3.to_checksum_address(self.STAKING_ROUTER_ADDRESS),
                "data": calldata,
                "gas": int(estimated_gas * 1.2),
                "maxFeePerGas": int(max_fee),
                "maxPriorityFeePerGas": int(max_priority_fee),
                "nonce": self.used_nonce[address],
                "chainId": web3.eth.chain_id,
            }

            tx_hash = await self.send_raw_transaction_with_retries(account, web3, tx)
            receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)

            block_number = receipt.blockNumber
            self.used_nonce[address] += 1

            return tx_hash, block_number
        except Exception as e:
            self.log(
                f"\033[36m\033[1m    Message :\033[0m"
                f"\033[91m\033[1m {str(e)} \033[0m"
            )
            return None, None
        
    async def print_timer(self):
        for remaining in range(random.randint(self.min_delay, self.max_delay), 0, -1):
            print(
                f"\033[36m\033[1m[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]\033[0m"
                f"\033[97m\033[1m | \033[0m"
                f"\033[94m\033[1mWait For\033[0m"
                f"\033[97m\033[1m {remaining} \033[0m"
                f"\033[94m\033[1mSeconds For Next Tx...\033[0m",
                end="\r",
                flush=True
            )
            await asyncio.sleep(1)

    def print_question(self):
        while True:
            try:
                staking_count = int(input("\033[93m\033[1mEnter Staking Count For Each Wallets -> \033[0m").strip())
                if staking_count > 0:
                    self.staking_count = staking_count
                    break
                else:
                    print("\033[91m\033[1mPlease enter positive number.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a number.\033[0m")

        while True:
            try:
                usdc_amount = float(input("\033[93m\033[1mEnter USDC Amount -> \033[0m").strip())
                if usdc_amount > 0:
                    self.usdc_amount = usdc_amount
                    break
                else:
                    print("\033[91m\033[1mAmount must be greater than 0.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a float or decimal number.\033[0m")

        while True:
            try:
                usdt_amount = float(input("\033[93m\033[1mEnter USDT Amount -> \033[0m").strip())
                if usdt_amount > 0:
                    self.usdt_amount = usdt_amount
                    break
                else:
                    print("\033[91m\033[1mAmount must be greater than 0.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a float or decimal number.\033[0m")

        while True:
            try:
                musd_amount = float(input("\033[93m\033[1mEnter MockUSD Amount -> \033[0m").strip())
                if musd_amount > 0:
                    self.musd_amount = musd_amount
                    break
                else:
                    print("\033[91m\033[1mAmount must be greater than 0.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a float or decimal number.\033[0m")

        while True:
            try:
                min_delay = int(input("\033[93m\033[1mMin Delay Each Tx -> \033[0m").strip())
                if min_delay >= 0:
                    self.min_delay = min_delay
                    break
                else:
                    print("\033[91m\033[1mMin Delay must be >= 0.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a number.\033[0m")

        while True:
            try:
                max_delay = int(input("\033[93m\033[1mMax Delay Each Tx -> \033[0m").strip())
                if max_delay >= self.min_delay:
                    self.max_delay = max_delay
                    break
                else:
                    print("\033[91m\033[1mMax Delay must be >= Min Delay.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a number.\033[0m")

        while True:
            try:
                print("\033[97m\033[1m1. Run With Free Proxyscrape Proxy\033[0m")
                print("\033[97m\033[1m2. Run With Private Proxy\033[0m")
                print("\033[97m\033[1m3. Run Without Proxy\033[0m")
                choose = int(input("\033[94m\033[1mChoose [1/2/3] -> \033[0m").strip())

                if choose in [1, 2, 3]:
                    proxy_type = (
                        "With Free Proxyscrape" if choose == 1 else 
                        "With Private" if choose == 2 else 
                        "Without"
                    )
                    print(f"\033[92m\033[1mRun {proxy_type} Proxy Selected.\033[0m")
                    break
                else:
                    print("\033[91m\033[1mPlease enter either 1, 2 or 3.\033[0m")
            except ValueError:
                print("\033[91m\033[1mInvalid input. Enter a number (1, 2 or 3).\033[0m")

        rotate = False
        if choose in [1, 2]:
            while True:
                rotate = input("\033[94m\033[1mRotate Invalid Proxy? [y/n] -> \033[0m").strip().lower()

                if rotate in ["y", "n"]:
                    rotate = rotate == "y"
                    break
                else:
                    print("\033[91m\033[1mInvalid input. Enter 'y' or 'n'.\033[0m")

        return choose, rotate
    
    async def check_connection(self, proxy_url=None):
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=10)) as session:
                async with session.get(url="https://api.ipify.org?format=json", proxy=proxy, proxy_auth=proxy_auth) as response:
                    response.raise_for_status()
                    return True
        except (Exception, ClientResponseError) as e:
            self.log(
                f"\033[36m\033[1mStatus  :\033[0m"
                f"\033[91m\033[1m Connection Not 200 OK \033[0m"
                f"\033[95m\033[1m-\033[0m"
                f"\033[93m\033[1m {str(e)} \033[0m"
            )
            return None
            
    async def financial_portfolio_recommendation(self, address: str, use_proxy: bool, retries=5):
        url = f"{self.BASE_API}/investment/financial-portfolio-recommendation"
        data = json.dumps(self.generate_recommendation_payload(address))
        headers = {
            **self.HEADERS,
            "Authorization": self.auth_tokens[address],
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        await asyncio.sleep(3)
        for attempt in range(retries):
            proxy_url = self.get_next_proxy_for_account(address) if use_proxy else None
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries:
                    await asyncio.sleep(5)
                    continue
                return None
            
    async def generate_change_transactions(self, address: str, change_tx: list, use_proxy: bool, retries=5):
        url = f"{self.BASE_API}/investment/generate-change-transactions"
        data = json.dumps(self.generate_transactions_payload(address, change_tx))
        headers = {
            **self.HEADERS,
            "Authorization": self.auth_tokens[address],
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        await asyncio.sleep(3)
        for attempt in range(retries):
            proxy_url = self.get_next_proxy_for_account(address) if use_proxy else None
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries:
                    await asyncio.sleep(5)
                    continue
                return None
        
    async def process_check_connection(self, address: str, use_proxy: bool, rotate_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(address) if use_proxy else None
            self.log(
                f"\033[36m\033[1mProxy   :\033[0m"
                f"\033[97m\033[1m {proxy} \033[0m"
            )

            is_valid = await self.check_connection(proxy)
            if not is_valid:
                if rotate_proxy:
                    proxy = self.rotate_proxy_for_account(address)
                    continue

                return False
            
            return True
    
    async def process_perform_claim_faucet(self, account: str, address: str, use_proxy: bool):
        next_faucet_claim_time = await self.get_next_faucet_claim_time(address, use_proxy)
        if next_faucet_claim_time is not None:
            if int(time.time()) >= next_faucet_claim_time:
                tx_hash, block_number = await self.perform_claim_faucet(account, address, use_proxy)
                if tx_hash and block_number:
                    explorer = f"https://testnet.pharosscan.xyz/tx/{tx_hash}"

                    self.log(
                        f"\033[36m\033[1m    Status  :\033[0m"
                        f"\033[92m\033[1m Success \033[0m"
                    )
                    self.log(
                        f"\033[36m\033[1m    Block   :\033[0m"
                        f"\033[97m\033[1m {block_number} \033[0m"
                    )
                    self.log(
                        f"\033[36m\033[1m    Tx Hash :\033[0m"
                        f"\033[97m\033[1m {tx_hash} \033[0m"
                    )
                    self.log(
                        f"\033[36m\033[1m    Explorer:\033[0m"
                        f"\033[97m\033[1m {explorer} \033[0m"
                    )
                
                else:
                    self.log(
                        f"\033[36m\033[1m    Status  :\033[0m"
                        f"\033[91m\033[1m Perform On-Chain Failed \033[0m"
                    )
            else:
                formatted_next_claim = datetime.fromtimestamp(next_faucet_claim_time).astimezone(wib).strftime("%x %X %Z")
                self.log(
                    f"\033[36m\033[1m    Status  :\033[0m"
                    f"\033[93m\033[1m Already Claimed \033[0m"
                    f"\033[95m\033[1m-\033[0m"
                    f"\033[36m\033[1m Next Claim at \033[0m"
                    f"\033[97m\033[1m{formatted_next_claim}\033[0m"
                )

    async def process_perform_staking(self, account: str, address: str, use_proxy: bool):
        portfolio = await self.financial_portfolio_recommendation(address, use_proxy)
        if portfolio:
            change_tx = portfolio["data"]["changes"]

            tx_hash, block_number = await self.perform_staking(account, address, change_tx, use_proxy)
            if tx_hash and block_number:
                explorer = f"https://testnet.pharosscan.xyz/tx/{tx_hash}"

                self.log(
                    f"\033[36m\033[1m    Status  :\033[0m"
                    f"\033[92m\033[1m Success \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m    Block   :\033[0m"
                    f"\033[97m\033[1m {block_number} \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m    Tx Hash :\033[0m"
                    f"\033[97m\033[1m {tx_hash} \033[0m"
                )
                self.log(
                    f"\033[36m\033[1m    Explorer:\033[0m"
                    f"\033[97m\033[1m {explorer} \033[0m"
                )
            
            else:
                self.log(
                    f"\033[36m\033[1m    Status  :\033[0m"
                    f"\033[91m\033[1m Perform On-Chain Failed \033[0m"
                )
        else:
            self.log(
                f"\033[36m\033[1m    Status  :\033[0m"
                f"\033[91m\033[1m GET Financial Portfolio Recommendation Failed \033[0m"
            )

    async def process_accounts(self, account: str, address: str, use_proxy: bool, rotate_proxy: bool):
        is_valid = await self.process_check_connection(address, use_proxy, rotate_proxy)
        if is_valid:
            web3 = await self.get_web3_with_check(address, use_proxy)
            if not web3:
                self.log(
                    f"\033[36m\033[1mStatus  :\033[0m"
                    f"\033[91m\033[1m Web3 Not Connected \033[0m"
                )
                return
            
            self.used_nonce[address] = web3.eth.get_transaction_count(address, "pending")

            self.log("\033[36m\033[1mFaucet  :\033[0m")

            await self.process_perform_claim_faucet(account, address, use_proxy)

            self.log("\033[36m\033[1mStaking :\033[0m")

            for i in range(self.staking_count):
                self.log(
                    f"\033[92m\033[1m ●\033[0m"
                    f"\033[94m\033[1m Stake \033[0m"
                    f"\033[97m\033[1m{i+1}\033[0m"
                    f"\033[95m\033[1m Of \033[0m"
                    f"\033[97m\033[1m{self.staking_count}\033[0m                                   "
                )

                self.log("\033[36m\033[1m    Balance :\033[0m")

                usdc_balance = await self.get_token_balance(address, self.USDC_CONTRACT_ADDRESS, use_proxy)
                self.log(
                    f"\033[95m\033[1m       1.\033[0m"
                    f"\033[97m\033[1m {usdc_balance} USDC \033[0m"
                )
                usdt_balance = await self.get_token_balance(address, self.USDT_CONTRACT_ADDRESS, use_proxy)
                self.log(
                    f"\033[95m\033[1m       2.\033[0m"
                    f"\033[97m\033[1m {usdt_balance} USDT \033[0m"
                )
                musd_balance = await self.get_token_balance(address, self.MUSD_CONTRACT_ADDRESS, use_proxy)
                self.log(
                    f"\033[95m\033[1m       3.\033[0m"
                    f"\033[97m\033[1m {musd_balance} MockUSD \033[0m"
                )

                self.log("\033[36m\033[1m    Amount  :\033[0m")
                self.log(
                    f"\033[95m\033[1m       1.\033[0m"
                    f"\033[97m\033[1m {self.usdc_amount} USDC \033[0m"
                )
                self.log(
                    f"\033[95m\033[1m       2.\033[0m"
                    f"\033[97m\033[1m {self.usdt_amount} USDT \033[0m"
                )
                self.log(
                    f"\033[95m\033[1m       3.\033[0m"
                    f"\033[97m\033[1m {self.musd_amount} MockUSD \033[0m"
                )

                if not usdc_balance or usdc_balance < self.usdc_amount:
                    self.log(
                        f"\033[36m\033[1m     Status  :\033[0m"
                        f"\033[93m\033[1m Insufficient USDC Token Balance \033[0m"
                    )
                    break

                if not usdt_balance or usdt_balance < self.usdt_amount:
                    self.log(
                        f"\033[36m\033[1m     Status  :\033[0m"
                        f"\033[93m\033[1m Insufficient USDT Token Balance \033[0m"
                    )
                    break

                if not musd_balance or musd_balance < self.musd_amount:
                    self.log(
                        f"\033[36m\033[1m     Status  :\033[0m"
                        f"\033[93m\033[1m Insufficient MockUSD Token Balance \033[0m"
                    )
                    break

                await self.process_perform_staking(account, address, use_proxy)
                await self.print_timer()
            
    async def main(self):
        try:
            with open("accounts.txt", "r") as file:
                accounts = [line.strip() for line in file if line.strip()]
            
            use_proxy_choice, rotate_proxy = self.print_question()

            while True:
                use_proxy = False
                if use_proxy_choice in [1, 2]:
                    use_proxy = True

                self.clear_terminal()
                self.welcome()
                self.log(
                    f"\033[92m\033[1mAccount's Total: \033[0m"
                    f"\033[97m\033[1m{len(accounts)}\033[0m"
                )

                if use_proxy:
                    await self.load_proxies(use_proxy_choice)
                
                separator = "=" * 25
                for account in accounts:
                    if account:
                        address = self.generate_address(account)

                        self.log(
                            f"\033[36m\033[1m{separator}[\033[0m"
                            f"\033[97m\033[1m {self.mask_account(address)} \033[0m"
                            f"\033[36m\033[1m]{separator}\033[0m"
                        )

                        if not address:
                            self.log(
                                f"\033[36m\033[1mStatus  :\033[0m"
                                f"\033[91m\033[1m Invalid Private Key or Library Version Not Supported \033[0m"
                            )
                            continue

                        self.auth_tokens[address] = self.generate_auth_token(address)
                        if not self.auth_tokens[address]:
                            self.log(
                                f"\033[36m\033[1mStatus  :\033[0m"
                                f"\033[91m\033[1m Cryptography Library Version Not Supported \033[0m"
                            )
                            continue

                        await self.process_accounts(account, address, use_proxy, rotate_proxy)
                        await asyncio.sleep(3)

                self.log("\033[36m\033[1m=\033[0m"*72)
                seconds = 24 * 60 * 60
                while seconds > 0:
                    formatted_time = self.format_seconds(seconds)
                    print(
                        f"\033[36m\033[1m[ Wait for\033[0m"
                        f"\033[97m\033[1m {formatted_time} \033[0m"
                        f"\033[36m\033[1m... ]\033[0m"
                        f"\033[97m\033[1m | \033[0m"
                        f"\033[94m\033[1mAll Accounts Have Been Processed.\033[0m",
                        end="\r"
                    )
                    await asyncio.sleep(1)
                    seconds -= 1

        except FileNotFoundError:
            self.log("\033[91mFile 'accounts.txt' Not Found.\033[0m")
            return
        except Exception as e:
            self.log(f"\033[91m\033[1mError: {e}\033[0m")
            raise e

if __name__ == "__main__":
    try:
        bot = AutoStaking()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(
            f"\033[36m\033[1m[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]\033[0m"
            f"\033[97m\033[1m | \033[0m"
            f"\033[91m\033[1m[ EXIT ] AutoStaking - BOT\033[0m                                       "                              
        )
