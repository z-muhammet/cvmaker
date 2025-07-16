import os  
import logging
from dotenv import load_dotenv  
import motor.motor_asyncio
from typing import Any, Dict, List  
from datetime import datetime

load_dotenv()  
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")  
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")

logging.basicConfig(level = logging.INFO)  
logger = logging.getLogger(__name__)

class dbManager:
  def __init__( self, uri : str, dbName : str ):
    self.clt = motor.motor_asyncio.AsyncIOMotorClient( uri )  
    self.db = self.clt[ dbName ]

  
  async def InsertMany( self, col : str, docs : List[Dict[str, Any]] ):
    clnDocs = []
    for d in docs:  
      d = dict( d )
      d.pop('_id', None)  
      clnDocs.append( d )  
    if ( clnDocs ):
      try:
        await self.db[ col ].insert_many( clnDocs )  
        logger.info( f"Inserted {len(clnDocs)} documents into {col}." )  
      except Exception as exc:  
        logger.error( f"Failed to insert many into {col}: {exc}" )  

  async def InsertOne( self, col : str, doc : Dict[str, Any] ):
    d = dict( doc )  
    d.pop('_id', None)  
    try:  
      await self.db[ col ].insert_one( d )
      logger.info( f"Inserted one document into {col}." )  
    except Exception as exc:  
      logger.error( f"Failed to insert one into {col}: {exc}" )  

  async def FindMany( self, c : str, q : Dict[str, Any], lim : int = 0 ) -> List[Dict[str, Any]]:
    try:  
      cur = self.db[ c ].find( q )
      if( lim > 0 ):
        cur = cur.limit( lim )  
      res = await cur.to_list( length = lim or 1000 )  
      logger.info( f"Found {len(res)} documents in {c}." )  
      return res  
    except Exception as exc:  
      logger.error( f"Failed to find many in {c}: {exc}" )  
      return []  

  async def FindOne( self, c : str, q : Dict[str, Any], s : list = None ) -> Dict[str, Any]:
    try:  
      cur = self.db[ c ].find( q )  
      if (s):
        cur = cur.sort( s )  
      res = await cur.to_list( length = 1 )  
      if ( res ):
        logger.info( f"Found one document in {c}." )  
        return res[0]  
      else:
        logger.info( f"No document found in {c}." )  
        return None  
    except Exception as exc:  
      logger.error( f"Failed to find one in {c}: {exc}" )  
      return None  

  async def UpdateOne( self, c : str, q : Dict[str, Any], update : Dict[str, Any], upsert : bool = False ):
    try:  
      res = await self.db[ c ].update_one( q, update, upsert = upsert )  
      logger.info( f"Updated one document in {c}." )  
      return res  
    except Exception as exc:  
      logger.error( f"Failed to update one in {c}: {exc}" )  
      return None  

  async def DeleteOne( self, c : str, q : Dict[str, Any] ):
    try:  
      await self.db[ c ].delete_one( q )  
      logger.info( f"Deleted one document from {c}." )  
    except Exception as exc:  
      logger.error( f"Failed to delete one from {c}: {exc}" )  

  async def DeleteMany( self, c : str, q : Dict[str, Any] ):
    try:  
      await self.db[ c ].delete_many( q )  
      logger.info( f"Deleted many documents from {c}." )  
    except Exception as exc:  
      logger.error( f"Failed to delete many from {c}: {exc}" )  

  async def GetColCount( self, c : str ) -> int:
    try:  
      cnt = await self.db[ c ].count_documents( {} )  
      logger.info( f"Collection {c} has {cnt} documents." )  
      return cnt  
    except Exception as exc:  
      logger.error( f"Failed to count documents in {c}: {exc}" )  
      return 0  

  async def RemoveOldProx( self, c : str, cut : datetime ) -> int:
    try:  
      res = await self.db[ c ].delete_many( { "added_at": { "$lt": cut } } )  
      logger.info( f"Removed {res.deleted_count} old proxies from {c}." )  
      return res.deleted_count  
    except Exception as exc:  
      logger.error( f"Failed to remove old proxies from {c}: {exc}" )  
      return 0  

  async def UpdateProxyTs( self, c : str, p : str ):
    try:  
      await self.db[ c ].update_one( { "proxy": p }, { "$set": { "last_tested": datetime.now() } }, upsert = True )  
      logger.info( f"Updated proxy timestamp for {p} in {c}." )  
    except Exception as exc:  
      logger.error( f"Failed to update proxy timestamp for {p} in {c}: {exc}" )  

db = dbManager( MONGODB_URI, MONGODB_DB ) 