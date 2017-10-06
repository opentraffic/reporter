package io.opentraffic.reporter;

import java.util.Properties;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;
import org.apache.commons.cli.Options;
import org.apache.commons.cli.ParseException;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.processor.TopologyBuilder;
import org.apache.kafka.streams.processor.WallclockTimestampExtractor;

/*
So the system we are attempting to build here looks like the following:

              raw                 formatted                      segments               time_quantised_tiled_segments       storage
kafka_stream -----> key_reformat -----------> windowed_mapmatch ----------> anonymiser -------------------------------\    =========
                    key_reformat              windowed_mapmatch             anonymiser --------------------------------\   |_______|
                         .                            .                         .      ---------------------------------\  |_______|
                         .                            .                         .      ---------------------------------/  |_______|
                    key_reformat              windowed_mapmatch             anonymiser --------------------------------/   |       |
                    key_reformat              windowed_mapmatch             anonymiser -------------------------------/    =========
                          
Basically we suck messages off of a stream configured by topic. We setup up some key_reformatter stream
processors to take the incoming messages, key them and reformat them to a standard internal format. From
there we have some windowed_mapmatch stream processors which will take windows of a given individuals
gps trace and match them to the route network to get back which osmlr segments were traversed, at what
times etc. We then send that onto an accumulating stream processor which will accumulate observations
up to a certain count over a certain period of time (to ensure privacy). Those are sent to a final
processor to batch them by the tile they occur in and move them onto an external location (http or file).
 */

public class Reporter {
  
  public static CommandLine parse(String[] args) {
    Option bootstrap = new Option("b", "bootstrap", true, "Bootstrap servers config");
    bootstrap.setRequired(true);
    
    Option topics = new Option("t", "topics", true, "A comma separated list of topics listed in the order they are operated on in the kafka stream."
        + "The first topic is the raw unformatted input messages. The second is the formatted messages. "
        + "The third is segments. The fourth is the anonymised segments.");
    topics.setRequired(true);
    
    Option formatter = new Option("f", "formatter", true, "The formatter configuration separated args for constructing a custom formatter.\n"
        + "Separated value and json are currently supported.\n"
        + "To construct a seprated value formatter where the raw messages look like:\n"
        + "  2017-01-31 16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|lat|lon|x|x|x\n"
        + "Specify a value of:\n"
        + "  --formatter \",sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss\"\n"
        + "To construct a json formatter where the raw messages look like:\n"
        + "  {\"timestamp\":1495037969,\"id\":\"uuid_abcdef\",\"accuracy\":51.305,\"latitude\":3.465725,\"longitude\":-76.5135033}\n"
        + "Specify a value of:\n"
        + "  --formatter \",json,id,latitude,longitude,timestamp,accuracy\"\n"
        + "Note that the time format string is optional, ie when your time value is already in epoch seconds.");
    formatter.setRequired(true);
    
    Option url = new Option("u", "reporter-url", true, "The url to send batched/windowed portions of a given keys points to.");
    url.setRequired(true);
    
    Option mode = new Option("m", "mode", true, "The mode of travel the input data used. Defaults to auto(mobile)");
    mode.setRequired(false);
    
    Option privacy = new Option("p", "privacy", true, "The minimum number of observations of a given segment pair "
        + "required before including this pair in the histogram.");
    privacy.setRequired(true);
    privacy.setType(Integer.class);
    
    Option quantisation = new Option("q", "quantisation", true, "The granularity, in seconds, at which to combine observations into as single tile. "
        + "Setting this to 3600 will result in tiles where all segment pairs occuring within a given hour will be in the same tile. Do not set this parameter "
        + "higher than the flush interval parameter. Doing so could result in tiles with very few segment pairs");
    quantisation.setRequired(true);
    quantisation.setType(Integer.class);
    
    Option interval = new Option("i", "flush-interval", true, "The interval, in seconds, at which tiles are flushed to storage. "
        + "Do not set this parameter lower than the quantisation. Doing so could result in tiles with very few segment pairs.");
    interval.setRequired(true);
    interval.setType(Integer.class);
    
    Option source = new Option("s", "source", true, "The name used in the tiles as a means of identifying the source of the data.");
    source.setRequired(true);
    
    Option output = new Option("o", "output-location", true, "A location to put the output histograms. "
        + "This can either be an http://location to POST to or /a/directory to write files to. "
        + "If its of the form https://*.amazonaws.com its assumed to be an s3 bucket and you'll need to have "
        + "the environment variables AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY properly set.");
    output.setRequired(true);

    Option duration = new Option("d", "duration", true, "How long to run the program in seconds, defaults to (essentially) forever.");
    duration.setRequired(false);
    duration.setType(Integer.class);
    
    Options options = new Options();
    options.addOption(bootstrap);
    options.addOption(topics);
    options.addOption(formatter);
    options.addOption(url);
    options.addOption(mode);
    options.addOption(privacy);
    options.addOption(quantisation);
    options.addOption(interval);
    options.addOption(source);
    options.addOption(output);
    options.addOption(duration);

    CommandLineParser parser = new DefaultParser();
    HelpFormatter help = new HelpFormatter();
    CommandLine cmd = null;

    try {
      cmd = parser.parse(options, args);
    }
    catch (ParseException e) {
      System.out.println(e.getMessage());
      help.printHelp("kafka-reporter", options);
      System.exit(1);
    }
    return cmd;
  }
  
  public static void main(String[] args) throws Exception {
    CommandLine cmd = parse(args);
    
    Properties props = new Properties();
    //for now lets just start streaming from the beginning instead of coming in mid stream
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
    //some init
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "reporter");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, cmd.getOptionValue("bootstrap"));
    props.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.TIMESTAMP_EXTRACTOR_CLASS_CONFIG, WallclockTimestampExtractor.class.getName());
    
    String[] topics = cmd.getOptionValue("topics").split(",");
    if(topics.length < 3)
      throw new RuntimeException("Wrong number of topics");

    //hook stuff together
    TopologyBuilder builder = new TopologyBuilder();
    
    //takes raw input from tnc and reformat the tnc format data into
    //a key of string type and a value of Point type
    builder.addSource("FormatterSource", new StringDeserializer(), new StringDeserializer(), topics[0]);
    builder.addProcessor("Formatter", new KeyedFormattingProcessor(cmd), "FormatterSource");
    Point.Serder pointSerder = new Point.Serder();
    builder.addSink("FormatterSink", topics[1], new StringSerializer(), pointSerder.serializer(), "Formatter");
    
    //take batches of points for a given key (uuid) and when some threshold is met
    //send that batch of points off to the reporter to be matched and update the
    //batch according to how much of the batch was used in matching
    builder.addSource("BatcherSource", new StringDeserializer(), pointSerder.deserializer(), topics[1]);
    builder.addProcessor("Batcher", new BatchingProcessor(cmd), "BatcherSource");
    builder.addStateStore(BatchingProcessor.GetStore(), "Batcher");
    Segment.Serder segmentSerder = new Segment.Serder();
    builder.addSink("BatcherSink", topics[2], new StringSerializer(), segmentSerder.serializer(), "Batcher");
    
    //takes individual osmlr segment pairs and accumulates them over a period of time
    //so as to provide some level of anonymity. after reaching sufficient anonymisation
    //it forwards the pair onto to be sent to the datastore
    builder.addSource("AnonymiserSource", new StringDeserializer(), segmentSerder.deserializer(), topics[2]);
    builder.addProcessor("Anonymiser", new AnonymisingProcessor(cmd), "AnonymiserSource");
    builder.addStateStore(AnonymisingProcessor.GetTileStore(), "Anonymiser");
    builder.addStateStore(AnonymisingProcessor.GetMapStore(), "Anonymiser");
    
    //start the topology
    KafkaStreams streams = new KafkaStreams(builder, props);
    streams.start();
    
    //wait a bit or basically forever
    long duration = 1000L * Integer.parseInt(cmd.getOptionValue("duration", Integer.toString(Integer.MAX_VALUE)));
    Thread.sleep(duration);

    //done
    pointSerder.close();
    segmentSerder.close();
    streams.close();
  }
}