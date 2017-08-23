package io.opentraffic.reporter;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.apache.commons.cli.CommandLine;
import org.apache.http.entity.ContentType;
import org.apache.http.entity.StringEntity;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.processor.Processor;
import org.apache.kafka.streams.processor.ProcessorContext;
import org.apache.kafka.streams.processor.ProcessorSupplier;
import org.apache.kafka.streams.processor.StateStoreSupplier;
import org.apache.kafka.streams.state.KeyValueIterator;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.Stores;
import org.apache.log4j.Logger;

public class AnonymisingProcessor implements ProcessorSupplier<String, Segment> {
  
  private final static Logger logger = Logger.getLogger(AnonymisingProcessor.class);
  private static final String ANONYMISER_TILE_STORE_NAME = "anonymise_tile_slices";
  private static final String ANONYMISER_MAP_STORE_NAME = "anonymise_max_slice";
  
  //so originally we stored just a map of the given tile to the list of all the segment pairs in the tile
  //this was great because it was simple, but the list can get pretty large over long time durations
  //the problem with a long list is that the size grows to the point that kafka doesnt want to store it
  //it likes to have "messages" (in this case values) which are less than 1mb in size
  //you can increase this but you'll have to make a guess as to what the max is supposed to be
  //its also unclear what raising this max does to other parts of the system, so we needed to work around it
  //the work around is to, when you run out of space, make a new place to store segments for the same tile
  //thats what we use the map below to do. we also do some naming tricks to make it easy to put all this
  //back together before we flush it to the datastore
  
  public static StateStoreSupplier<?> GetTileStore() {
    return Stores.create(ANONYMISER_TILE_STORE_NAME).
        withKeys(new TimeQuantisedTile.Serder()).
        withValues(new Segment.ListSerder()).
        inMemory().build();
  }
  
  public static StateStoreSupplier<?> GetMapStore() {
    return Stores.create(ANONYMISER_MAP_STORE_NAME).
        withKeys(new TimeQuantisedTile.Serder()).
        withIntegerValues().
        persistent().build();
  }

  private final int privacy;      //number of observations required to make it into a tile
  private final long interval;    //how frequently to dump tiles to external location
  private final int quantisation; //what is the resolution for time buckets
  private final String source;    //how we'll identify ourselves to the external datastore
  private final String output;    //where should the output go
  private final boolean bucket;   //if the output should go to an s3 bucket
  private final String aws_key;   //needed for s3 output
  private final String aws_secret;//needed for s3 output

  public AnonymisingProcessor(CommandLine cmd) {
    privacy = Integer.parseInt(cmd.getOptionValue("privacy"));
    if(privacy < 1)
      throw new RuntimeException("Need a privacy parameter of 1 or more");
    interval = 1000L * Integer.parseInt(cmd.getOptionValue("flush-interval"));
    if(interval < 60)
      throw new RuntimeException("Need an interval parameter of 60 or more");
    quantisation = Integer.parseInt(cmd.getOptionValue("quantisation"));
    if(quantisation < 60)
      throw new RuntimeException("Need quantisation parameter of 60 or more");
    output = cmd.getOptionValue("output-location").replaceAll("/+$", "");
    source = cmd.getOptionValue("source");
    
    File f = new File(output);
    bucket = output.endsWith("amazonaws.com");
    boolean http = output.startsWith("http://") || output.startsWith("https://");
    Map<String, String> env = System.getenv();
    aws_key = env.get("AWS_ACCESS_KEY_ID");
    aws_secret = env.get("AWS_SECRET_ACCESS_KEY");
    
    //if its a bucket but you didnt have keys
    if(bucket) {
      if(!http)
        throw new RuntimeException("Cannot PUT to " + output + " without https:// or http:// prefix");
      if(aws_key == null || aws_secret == null)
        throw new RuntimeException("Both env vars AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set to PUT to " + output);
    }//its not http and we couldnt make a directory
    else if(!http && !f.isDirectory() && !f.mkdirs())
      throw new RuntimeException("Cannot create output directory " + output);
  }

  @Override
  public Processor<String, Segment> get() {
    return new Processor<String, Segment>() {
      private ProcessorContext context;
      private KeyValueStore<TimeQuantisedTile, ArrayList<Segment>> store;
      private KeyValueStore<TimeQuantisedTile, Integer> map;
      
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.store = (KeyValueStore<TimeQuantisedTile, ArrayList<Segment>>) context.getStateStore(ANONYMISER_TILE_STORE_NAME);
        this.map = (KeyValueStore<TimeQuantisedTile, Integer>) context.getStateStore(ANONYMISER_MAP_STORE_NAME);
        this.context.schedule(interval);
        
        logger.error("Walking over map");
        KeyValueIterator<TimeQuantisedTile, Integer> k = map.all();
        while(k.hasNext()) {
          KeyValue<TimeQuantisedTile, Integer> tile = k.next();
          TimeQuantisedTile t = tile.key;
          t.tile_slice = tile.value;
          logger.error(t.toString());
        }
        k.close();
        
        logger.error("Walking over store");
        KeyValueIterator<TimeQuantisedTile, ArrayList<Segment>> j = store.all();
        while(j.hasNext()) {
          KeyValue<TimeQuantisedTile, ArrayList<Segment>> tile = j.next();
          logger.error(tile.key.toString());
        }
        j.close(); 
      }

      @Override
      public void process(String key, Segment value) {
        //for each time bucket this segment touches
        List<TimeQuantisedTile> tiles = TimeQuantisedTile.getTiles(value, quantisation);
        for(TimeQuantisedTile tile : tiles) {
          //turn the tile into a string name to get the current place we are dumping segments
          Integer slice = map.get(tile);
          if(slice == null) {
            logger.info("Starting quantised tile bucket " + tile.toString());
          }
          //get this segment from the store
          ArrayList<Segment> segments = store.get(tile);
          //if its not there make one
          if(segments == null)
            segments = new ArrayList<Segment>(1);
          //keep this new one
          segments.add(value);
          //put it back in the store
          try {
            if(segments.size() > 20000)
              throw new Exception("limiting the size");
            store.put(tile, segments);
            map.put(tile, tile.tile_slice);
          }//or fail and flush to sync
          catch (Exception e) {
            logger.error("Couldnt store " + Integer.toString(segments.size()) + " segments");
            //new list of segments starting with the one that didnt fit
            segments = new ArrayList<Segment>(1);
            segments.add(value);
            //update the stores with this info
            tile.tile_slice++;
            logger.info("Starting quantised tile bucket for " + tile.toString());
            store.put(tile, segments);
            //the tile without slice information points to which slice in the store
            slice = tile.tile_slice;
            tile.tile_slice = 0;
            map.put(tile, slice);
          }
        }
      }
      
      private void clean(ArrayList<Segment> segments) {
        //delete ranges of ids that dont have enough counts to make the privacy requirement
        int start = 0;
        for(int i = 0; i < segments.size(); i++) {
          Segment s = segments.get(start);
          Segment e = segments.get(i);
          //we are onto a new range or the last one
          if(s.id != e.id || s.next_id != e.next_id || i == segments.size() - 1) {
            //if its the last range we need i to be as if its the next segment pair
            if(i == segments.size() - 1)
              i++;
            //didnt make the cut
            if(i - start < privacy) {
              segments.subList(start,  i).clear();
              i = start;
            }//did make the cut
            else
              start = i;
          }
        }
      }
      
      private void store(TimeQuantisedTile tile, ArrayList<Segment> segments) {
        //build up the payload
        StringBuffer buffer = new StringBuffer(segments.size() * 64);
        buffer.append(Segment.columnLayout());
        for(Segment segment : segments)
          segment.appendToStringBuffer(buffer, source);
        
        //figure out some naming
        String tile_name = Long.toString(tile.time_range_start) + '_' +
            Long.toString(tile.time_range_start + quantisation - 1) + '/' + 
            Long.toString(tile.getTileLevel()) + '/' + Long.toString(tile.getTileIndex());
        String file_name = source + '.' + UUID.randomUUID().toString();
        
        //jettison the tiles to external storage
        try {
          //put it to s3
          if(bucket) {
            logger.info("PUTting tile to " + output + '/' + tile_name + '/' + file_name);
            StringEntity body = new StringEntity(buffer.toString(), ContentType.create("text/plain", Charset.forName("UTF-8")));
            HttpClient.AwsPUT(output, tile_name + '/' + file_name, body, aws_key, aws_secret);
          }//post it to non s3
          else if(output.startsWith("http://") || output.startsWith("https://")) {
            logger.info("POSTing tile to " + output + '/' + tile_name + '/' + file_name);
            StringEntity body = new StringEntity(buffer.toString(), ContentType.create("text/plain", Charset.forName("UTF-8")));
            HttpClient.POST(output + '/' + file_name, body);
          }//write a new file in a dir
          else {
            logger.info("Writing tile to " + output + '/' + tile_name + '/' + file_name);
            File dir = new File(output + '/' + tile_name);
            dir.mkdirs();
            File tile_file = new File(output + '/' + tile_name + '/' + file_name);
            BufferedWriter writer = new BufferedWriter(new FileWriter(tile_file));            
            writer.write(buffer.toString());
            writer.flush();
            writer.close();
          }
        }
        catch(Exception e) {
          logger.error("Couldn't flush tile to sync " + tile_name + "/" + file_name + ": " + e.getMessage());
        }
      }

      @Override
      public void punctuate(long timestamp) {
        logger.error("Walking over map");
        KeyValueIterator<TimeQuantisedTile, Integer> k = map.all();
        while(k.hasNext()) {
          KeyValue<TimeQuantisedTile, Integer> tile = k.next();
          TimeQuantisedTile t = tile.key;
          t.tile_slice = tile.value;
          logger.error(t.toString());
        }
        k.close();
        
        logger.error("Walking over store");
        KeyValueIterator<TimeQuantisedTile, ArrayList<Segment>> j = store.all();
        while(j.hasNext()) {
          KeyValue<TimeQuantisedTile, ArrayList<Segment>> tile = j.next();
          logger.error(tile.key.toString());
        }
        j.close();        
        
        //go through all the tile bucket combos
        KeyValueIterator<TimeQuantisedTile, ArrayList<Segment>> it = store.all();
        while(it.hasNext()) {
          //collect all the observations across all buckets for this tile
          TimeQuantisedTile tile = it.next().key;
          it.close();
          ArrayList<Segment> segments = new ArrayList<Segment>(10);
          ArrayList<Segment> slice;
          for(tile.tile_slice = 0; (slice = store.get(tile)) != null; tile.tile_slice++) {
            segments.addAll(slice);
            store.delete(tile);
          }
          //we purge the entire key value store, otherwise kvstore would have an enourmous long tail
          tile.tile_slice = 0;
          map.delete(tile);
          //sort it by the ids
          Collections.sort(segments);
          //delete segment pairs that dont meet the privacy requirement
          clean(segments);
          //store this tile if it has data
          if(!segments.isEmpty())
            store(tile, segments);
          //next tile
          it = store.all();
        }
        it.close();
      }

      @Override
      public void close() {
        punctuate(0);
      }
      
    };
  }
}
