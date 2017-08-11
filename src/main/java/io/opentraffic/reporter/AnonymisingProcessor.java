package io.opentraffic.reporter;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;
import java.util.UUID;

import org.apache.commons.cli.CommandLine;
import org.apache.http.Header;
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
  private static final String ANONYMISER_STORE_NAME = "anonymise";
  public static StateStoreSupplier<?> GetStore() {
    return Stores.create(ANONYMISER_STORE_NAME).
        withKeys(new TimeQuantisedTile.Serder()).
        withValues(new Segment.ListSerder()).
        inMemory().build();
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
      
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.store = (KeyValueStore<TimeQuantisedTile, ArrayList<Segment>>) context.getStateStore(ANONYMISER_STORE_NAME);
        this.context.schedule(interval);
      }

      @Override
      public void process(String key, Segment value) {
        //for each time bucket this segment touches
        List<TimeQuantisedTile> tiles = TimeQuantisedTile.getTiles(value, quantisation);
        for(TimeQuantisedTile tile : tiles) {
          //get this segment from the store
          ArrayList<Segment> segments = store.get(tile);
          //if its not there make one
          if(segments == null)
            segments = new ArrayList<Segment>(1);
          //keep this new one
          segments.add(value);
          //put it back in the store
          store.put(tile, segments);
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
            logger.debug("PUTting tile to " + output + '/' + tile_name + '/' + file_name);
            StringEntity body = new StringEntity(buffer.toString(), ContentType.create("text/plain", Charset.forName("UTF-8")));
            HttpClient.AwsPUT(output, tile_name + '/' + file_name, body, aws_key, aws_secret);
          }//post it to non s3
          else if(output.startsWith("http://") || output.startsWith("https://")) {
            logger.debug("POSTing tile to " + output + '/' + tile_name + '/' + file_name);
            StringEntity body = new StringEntity(buffer.toString(), ContentType.create("text/plain", Charset.forName("UTF-8")));
            HttpClient.POST(output + '/' + file_name, body);
          }//write a new file in a dir
          else {
            logger.debug("Writing tile to " + output + '/' + tile_name + '/' + file_name);
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
          logger.error("Couldn't write " + tile_name + "/" + file_name + ": " + e.getMessage());
        }
      }

      @Override
      public void punctuate(long timestamp) {
        //go through all the tiles
        KeyValueIterator<TimeQuantisedTile, ArrayList<Segment> > it = store.all();
        while(it.hasNext()) {
          //if we meet the privacy requirement allow this segment into the tile
          KeyValue<TimeQuantisedTile, ArrayList<Segment>> kv = it.next();
          //sort it by the ids
          Collections.sort(kv.value);
          //delete segment pairs that dont meet the privacy requirement
          clean(kv.value);
          //store this tile
          store(kv.key, kv.value);
        }
        it.close();
        //we purge the entire key value store, otherwise kvstore would have an enourmous long tail
        store.flush();        
      }

      @Override
      public void close() {
        punctuate(0);
      }
      
    };
  }
}
