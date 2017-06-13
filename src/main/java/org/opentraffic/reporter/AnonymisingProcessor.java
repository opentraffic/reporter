package org.opentraffic.reporter;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.Charset;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;
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
  private static final String ANONYMISER_STORE_NAME = "anonymise";
  public static StateStoreSupplier<?> GetStore() {
    return Stores.create(ANONYMISER_STORE_NAME).
        withKeys(new TimeQuantisedTiledSegmentPair.Serder()).
        withValues(new Segment.Serder()).
        inMemory().build();
  }
  private final int privacy;      //number of observations required to make it into a tile
  private final long interval;    //how frequently to dump tiles to external location
  private final int quantisation; //what is the resolution for time buckets
  private final String source;    //how we'll identify ourselves to the external datastore
  private final String output;    //where should the output go
  

  public AnonymisingProcessor(CommandLine cmd) {
    this.privacy = Integer.parseInt(cmd.getOptionValue("privacy"));
    if(privacy < 1)
      throw new RuntimeException("Need a privacy parameter of 1 or more");
    this.interval = 1000L * Integer.parseInt(cmd.getOptionValue("flush-interval"));
    if(interval < 60)
      throw new RuntimeException("Need an interval parameter of 60 or more");
    this.quantisation = Integer.parseInt(cmd.getOptionValue("quantisation"));
    if(quantisation < 60)
      throw new RuntimeException("Need quantisation parameter of 60 or more");
    this.output = cmd.getOptionValue("output-location");
    this.source = cmd.getOptionValue("source");
    
    //where will the tiles go    
    File f = new File(output);
    boolean http = output.startsWith("http://") || output.startsWith("https://");
    if(!http && !f.isDirectory() && !f.mkdirs())
      throw new RuntimeException("Cannot be created as a directory");
  }

  @Override
  public Processor<String, Segment> get() {
    return new Processor<String, Segment>() {
      private ProcessorContext context;
      private KeyValueStore<TimeQuantisedTiledSegmentPair, Segment> store;
      
      @SuppressWarnings("unchecked")
      @Override
      public void init(ProcessorContext context) {
        this.context = context;
        this.store = (KeyValueStore<TimeQuantisedTiledSegmentPair, Segment>) context.getStateStore(ANONYMISER_STORE_NAME);
        this.context.schedule(interval);
      }

      @Override
      public void process(String key, Segment value) {
        //for each time bucket this segment touches
        List<TimeQuantisedTiledSegmentPair> tiles = TimeQuantisedTiledSegmentPair.getTiles(value, quantisation);
        for(TimeQuantisedTiledSegmentPair tile : tiles) {
          //get this segment from the store
          Segment segment = store.get(tile);
          //if its not there make one
          if(segment == null)
            segment = value;
          //if it is combine them
          else
            segment.combine(value);
          //put it back in the store
          store.put(tile, segment);
        }
      }

      @Override
      public void punctuate(long timestamp) {
        //a place to hold the tiles in memory...
        //TODO: figure out a way to use the range iterator and then just iterate over a given tiles time slices
        Map<String, StringBuffer> tiles = new HashMap<String, StringBuffer>();
        //go through all the segments
        KeyValueIterator<TimeQuantisedTiledSegmentPair, Segment> it = store.all();
        while(it.hasNext()) {
          //if we meet the privacy requirement allow this segment into the tile
          KeyValue<TimeQuantisedTiledSegmentPair, Segment> kv = it.next();
          TimeQuantisedTiledSegmentPair key = kv.key;
          Segment segment = kv.value;
          if(kv.value.count >= privacy) {
            String tile_name =  Long.toString(key.time_range_start) + '_' +
              Long.toString(key.time_range_start + quantisation - 1) + '/' + Long.toString(key.tile_id);
            StringBuffer tile = tiles.get(tile_name);
            if(tile == null) {
              tile = new StringBuffer();
              tiles.put(tile_name, tile);
            }
            segment.appendToStringBuffer(tile);
          }
          //we purge the entire key value store, otherwise kvstore would have an enourmous long tail
          //the store has no clear or pop or front methods, you cant delete while you iterate
          //maybe you could close it and make a new one but the api suggests against doing that
          it.close();
          store.delete(key);
          it = store.all();
        }
        it.close();
        
        //jettison the tiles to external storage
        String file_name = source + '.' + UUID.randomUUID().toString();
        Iterator<Entry<String, StringBuffer> > tile_it = tiles.entrySet().iterator();
        while(tile_it.hasNext()) {
          Entry<String, StringBuffer> kv = tile_it.next();
          //post it
          if(output.startsWith("http://") || output.startsWith("https://")) {
            logger.debug("POSTing tile to " + output + '/' + kv.getKey() + '/' + file_name);
            StringEntity body = new StringEntity(kv.getValue().toString(), ContentType.create("text/plain", Charset.forName("UTF-8")));
            HttpClient.POST(output + '/' + file_name, body);
          }//write a new file in a dir
          else {
            try {
              logger.debug("Writing tile to " + output + '/' + kv.getKey() + '/' + file_name);
              File dir = new File(output + '/' + kv.getKey());
              dir.mkdirs();
              File tile_file = new File(output + '/' + kv.getKey() + '/' + file_name);
              BufferedWriter writer = new BufferedWriter(new FileWriter(tile_file));            
              writer.write(kv.getValue().toString());
              writer.flush();
              writer.close();
            }
            catch(Exception e) {
              logger.error("Couldn't write tile: " + e.getMessage());
            }
          }
        }
        
      }

      @Override
      public void close() {
        punctuate(0);
      }
      
    };
  }
}
